"""RAG 用例流程：文档入库(切块→向量化→落库)与检索(向量化问题→查最近块)。

服务层只编排流程，SQL 在 repositories.documents，向量化在 agent.embedding。
资料按项目归属：同项目多 Agent 共享同一份资料，检索时按 project_id 圈定范围。
"""
from collections import defaultdict, deque
import math

import asyncpg

from app.agent.embedding import embed_query, embed_texts
from app.agent.rerank import rerank
from app.repositories import documents

# 每块约 300 字：块太大检索命中不精准，太小又丢上下文，取个够用的中间值。
CHUNK_SIZE = 300
# 召回阶段先多捞一些候选，再交给 rerank 精排出最终 top_k。
RECALL_SIZE = 20


def _split(content: str) -> list[str]:
    """按固定长度切块：最小可行策略，不做按句/重叠的复杂切分。"""
    text = content.strip()
    return [text[i : i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]


async def ingest_document(pool: asyncpg.Pool, project_id, title: str, content: str):
    """文档入库：切块→批量向量化→单事务写文档和所有块。

    单事务关键：文档和它的块要么全写成功、要么全不写，
    避免出现有文档没块(检索永远命中不到)或有块没文档(JOIN 丢数据)的半截状态。
    """
    chunks = _split(content)
    embeddings = await embed_texts(chunks)
    async with pool.acquire() as conn:
        async with conn.transaction():
            doc = await documents.insert_document(conn, project_id, title, content)
            await documents.insert_chunks(conn, doc["id"], chunks, embeddings)
    return doc["id"], len(chunks)


async def list_documents(pool: asyncpg.Pool, project_id) -> list[dict]:
    """列出某项目的资料（标题+块数），供资料管理页展示。"""
    async with pool.acquire() as conn:
        rows = await documents.list_documents_by_project(conn, project_id)
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "chunk_count": r["chunk_count"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


async def delete_document(pool: asyncpg.Pool, document_id) -> None:
    """删一篇资料（chunks 级联删除）。"""
    async with pool.acquire() as conn:
        await documents.delete_document(conn, document_id)


async def retrieve(
    pool: asyncpg.Pool, project_id, question: str, top_k: int = 3
) -> list[dict]:
    """两阶段检索：先向量召回 RECALL_SIZE 个候选，再 rerank 精排出 top_k。

    先召回后精排：向量检索快但粗，负责从全量里捞回可能相关的候选；
    rerank 慢但准，只在这一小批候选上做精细打分，兼顾速度与准确。
    返回每块的原文和所属文档标题，供前端「点击溯源」定位到具体来源文件。
    """
    query_embedding = await embed_query(question)
    async with pool.acquire() as conn:
        rows = await documents.search_chunks_with_doc(
            conn, project_id, query_embedding, RECALL_SIZE
        )
    # Keep a queue per text: duplicate chunks may belong to different documents.
    rows_by_content = defaultdict(deque)
    for row in rows:
        rows_by_content[row["content"]].append(row)
    candidates = [r["content"] for r in rows]
    ranked = await rerank(question, candidates, top_k)
    hits = []
    for content in ranked:
        row = rows_by_content[content].popleft()
        similarity = row["similarity"]
        # Floating point round-off can exceed cosine bounds; NaN must not enter JSON.
        similarity = max(-1.0, min(1.0, float(similarity))) if similarity is not None and math.isfinite(similarity) else None
        hits.append({
            "title": row["title"], "content": content,
            "document_id": str(row["document_id"]), "chunk_id": str(row["chunk_id"]),
            "similarity": similarity,
        })
    return hits
