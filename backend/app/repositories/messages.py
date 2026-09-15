"""messages 表的读写：每个函数就是一条明确的 SQL，不含业务判断。

函数统一接收 asyncpg 连接，由上层 service 决定何时开事务、按什么顺序调用。
"""
import asyncpg


async def insert_message(
    conn: asyncpg.Connection,
    thread_id: str,
    role: str,
    content: str,
    request_id=None,
) -> asyncpg.Record:
    """写入一条消息，返回库里生成的 id 与 created_at（用于「落库即返回」）。

    assistant 回复传入 request_id 绑定发起它的请求，SSE late-join 据此精确取回结果；
    user 消息不传，保持 NULL。
    """
    return await conn.fetchrow(
        """
        INSERT INTO messages (thread_id, role, content, request_id)
        VALUES ($1, $2, $3, $4)
        RETURNING id, thread_id, role, content, created_at
        """,
        thread_id,
        role,
        content,
        request_id,
    )


async def get_assistant_reply(
    conn: asyncpg.Connection, request_id
) -> asyncpg.Record | None:
    """取某请求对应的 assistant 回复；SSE 客户端晚连时从库里补发结果用。"""
    return await conn.fetchrow(
        """
        SELECT content
        FROM messages
        WHERE request_id = $1 AND role = 'assistant'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        request_id,
    )


async def list_messages_by_thread(
    conn: asyncpg.Connection, thread_id: str
) -> list[asyncpg.Record]:
    """按时间正序取出一个会话的全部消息，用于回放对话。"""
    return await conn.fetch(
        """
        SELECT id, thread_id, role, content, created_at
        FROM messages
        WHERE thread_id = $1
        ORDER BY created_at
        """,
        thread_id,
    )


async def delete_messages_by_threads(conn: asyncpg.Connection, thread_ids: list) -> None:
    """删项目时清理其会话名下的消息（先删引用它的请求再删这里）。"""
    await conn.execute(
        "DELETE FROM messages WHERE thread_id = ANY($1::text[])",
        thread_ids,
    )
