"""messages 表的读写：每个函数就是一条明确的 SQL，不含业务判断。

函数统一接收 asyncpg 连接，由上层 service 决定何时开事务、按什么顺序调用。
"""
import json
import asyncpg


async def insert_message(
    conn: asyncpg.Connection,
    thread_id: str,
    role: str,
    content: str,
    request_id=None,
    sources=None,
    steps=None,
) -> asyncpg.Record:
    """写入一条消息，返回库里生成的 id 与 created_at（用于「落库即返回」）。

    assistant 回复传入 request_id 绑定发起它的请求，SSE late-join 据此精确取回结果；
    user 消息不传，保持 NULL。
    """
    return await conn.fetchrow(
        """
        INSERT INTO messages (thread_id, role, content, request_id, sources, steps)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
        RETURNING id, thread_id, role, content, created_at
        """,
        thread_id,
        role,
        content,
        request_id,
        json.dumps(sources or [], ensure_ascii=False),
        json.dumps(steps or [], ensure_ascii=False),
    )


async def get_assistant_reply(
    conn: asyncpg.Connection, request_id
) -> asyncpg.Record | None:
    """取某请求对应的 assistant 回复；SSE 客户端晚连时从库里补发结果用。"""
    return await conn.fetchrow(
        """
        SELECT content, sources, steps
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
        SELECT id, thread_id, role, content, created_at, sources, steps
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

async def history_before_request(conn, thread_id, request_id):
    """只取当前请求之前已经成功的问答，避免带入排队中的未来问题。"""
    return await conn.fetch("""
        WITH previous AS (
            SELECT q.id, q.message_id, q.created_at
            FROM agent_run_requests q
            JOIN agent_run_requests current ON current.id = $2
            WHERE q.thread_id = $1 AND q.status = 'done'
              AND (q.created_at, q.id) < (current.created_at, current.id)
            ORDER BY q.created_at DESC, q.id DESC LIMIT 12
        )
        SELECT m.role, m.content FROM previous q
        JOIN messages m ON m.id = q.message_id OR (m.request_id = q.id AND m.role = 'assistant')
        ORDER BY q.created_at, q.id, CASE m.role WHEN 'user' THEN 0 ELSE 1 END
    """, thread_id, request_id)
