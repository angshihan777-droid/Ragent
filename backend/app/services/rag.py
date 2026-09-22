"""RAG 用例流程：文档入库(切块→向量化→落库)与检索(向量化问题→查最近块)。

服务层只编排流程，SQL 在 repositories.documents，向量化在 agent.embedding。
资料按项目归属：同项目多会话共享同一份资料，检索时按 project_id 圈定范围。
"""
from collections import defaultdict, deque
import math
import json

import asyncpg

from app.agent.embedding import embed_query, embed_texts, prepare_chunks
from app.services.attachments import text_blocks
from app.services.chunking import INDEX_VERSION
from app.agent.rerank import rerank
from app.repositories import documents

RECALL_SIZE = 20


async def ingest_document(pool, project_id, title, content=None, *, blocks=None, source_hash=None):
    if blocks is None:
        blocks = text_blocks(content or "", markdown=True)
    if not blocks:
        raise ValueError("资料内容不能为空")
    content = "\n\n".join(block["text"] for block in blocks)
    chunks = await prepare_chunks(blocks, title)
    embeddings = await embed_texts([chunk["content"] for chunk in chunks])
    async with pool.acquire() as conn:
        async with conn.transaction():
            if source_hash:
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", str(project_id) + source_hash)
                existing = await conn.fetchrow("SELECT d.id, (SELECT count(*) FROM chunks c WHERE c.document_id=d.id) AS count FROM documents d WHERE project_id=$1 AND source_hash=$2", project_id, source_hash)
                if existing:
                    return existing["id"], existing["count"]
            doc = await documents.insert_document(conn, project_id, title, content, blocks, INDEX_VERSION, source_hash)
            await documents.insert_chunks(conn, doc["id"], chunks, embeddings)
    return doc["id"], len(chunks)


async def reindex_documents(pool):
    """显式维护操作：按文档原子替换索引。旧纯文本不伪造页码/表格。"""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, title, content, blocks FROM documents WHERE index_version < $1", INDEX_VERSION)
    rebuilt = 0
    for row in rows:
        blocks = json.loads(row["blocks"]) if row["blocks"] else text_blocks(row["content"], markdown=row["title"].lower().endswith((".md", ".markdown")))
        chunks = await prepare_chunks(blocks, row["title"])
        embeddings = await embed_texts([c["content"] for c in chunks])
        async with pool.acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow("SELECT index_version FROM documents WHERE id=$1 FOR UPDATE", row["id"])
                if current is None or current["index_version"] >= INDEX_VERSION:
                    continue
                await conn.execute("DELETE FROM chunks WHERE document_id=$1", row["id"])
                await documents.insert_chunks(conn, row["id"], chunks, embeddings)
                await conn.execute("UPDATE documents SET blocks=$2::jsonb, index_version=$3 WHERE id=$1", row["id"], json.dumps(blocks, ensure_ascii=False), INDEX_VERSION)
                rebuilt += 1
    return rebuilt


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
    if not rows:
        return []
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
            "similarity": similarity, "metadata": json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
        })
    return hits
