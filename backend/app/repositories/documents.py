"""documents/chunks 表读写：文档入库与向量检索的 SQL，不含业务判断。

向量以 pgvector 文本字面量 '[v1,v2,...]' 传入，用 ::vector 显式转型——
asyncpg 无 pgvector 原生编码器，这是最小可行的传参方式。
"""
import asyncpg


def _to_vector_literal(vec: list[float]) -> str:
    """把浮点列表拼成 pgvector 字面量字符串，如 '[0.1,0.2]'。"""
    return "[" + ",".join(repr(x) for x in vec) + "]"


async def insert_document(
    conn: asyncpg.Connection, project_id, title: str, content: str
) -> asyncpg.Record:
    """写入一篇文档（归属项目），返回其 id。"""
    return await conn.fetchrow(
        """
        INSERT INTO documents (project_id, title, content)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        project_id,
        title,
        content,
    )


async def insert_chunks(
    conn: asyncpg.Connection,
    document_id,
    chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    """批量写入一篇文档的所有文本块及其向量。

    chunks 与 embeddings 一一对应；用 executemany 一次写完，减少往返。
    """
    rows = [
        (document_id, chunks[i], _to_vector_literal(embeddings[i]))
        for i in range(len(chunks))
    ]
    await conn.executemany(
        """
        INSERT INTO chunks (document_id, content, embedding)
        VALUES ($1, $2, $3::vector)
        """,
        rows,
    )


async def list_documents_by_project(
    conn: asyncpg.Connection, project_id
) -> list[asyncpg.Record]:
    """列出某项目下的资料（不含正文，列表页只需标题和块数）。"""
    return await conn.fetch(
        """
        SELECT d.id, d.title, d.created_at,
               (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS chunk_count
        FROM documents d
        WHERE d.project_id = $1
        ORDER BY d.created_at DESC
        """,
        project_id,
    )


async def delete_document(conn: asyncpg.Connection, document_id) -> None:
    """删一篇文档；它的 chunks 靠外键 ON DELETE CASCADE 一并清除。"""
    await conn.execute("DELETE FROM documents WHERE id = $1", document_id)


async def search_chunks_with_doc(
    conn: asyncpg.Connection, project_id, query_embedding: list[float], top_k: int
) -> list[asyncpg.Record]:
    """检索并带出每块所属文档标题，供离线评测判断「命中的是不是正确资料」。

    线上溯源与离线评测共用；同时返回真实余弦相似度及来源 ID。
    排序仍按向量距离，后续精排只改变顺序，不把相似度伪装成重排概率。
    """
    return await conn.fetch(
        """
        SELECT c.id AS chunk_id, d.id AS document_id, c.content, d.title,
               1 - (c.embedding <=> $2::vector) AS similarity
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.project_id = $1
        ORDER BY c.embedding <=> $2::vector
        LIMIT $3
        """,
        project_id,
        _to_vector_literal(query_embedding),
        top_k,
    )


async def search_chunks(
    conn: asyncpg.Connection, project_id, query_embedding: list[float], top_k: int
) -> list[asyncpg.Record]:
    """按余弦距离取最相近的 top_k 个文本块。

    <=> 是 pgvector 的余弦距离运算符，越小越相似；只在本项目的文档内检索。
    """
    return await conn.fetch(
        """
        SELECT c.content
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.project_id = $1
        ORDER BY c.embedding <=> $2::vector
        LIMIT $3
        """,
        project_id,
        _to_vector_literal(query_embedding),
        top_k,
    )
