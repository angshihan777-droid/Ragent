"""agent_run_requests 表的读写：用户视角的「请求账本」。

FIFO 排队所需的最小读写都在这里，函数只做单条 SQL，不判断能否派发。
"""
import asyncpg


async def insert_request(
    conn: asyncpg.Connection,
    user_id: str,
    agent_id: str,
    thread_id: str,
    message_id,
) -> asyncpg.Record:
    """落一条排队中的请求，返回 id 与状态（用于「落库即返回」立刻给前端 ID）。

    绑定 message_id：把请求和它对应的那条 user 消息钉死，
    worker 执行时按 request 拿到确切问题，避免多条请求排队时读串。
    """
    return await conn.fetchrow(
        """
        INSERT INTO agent_run_requests (user_id, agent_id, thread_id, message_id)
        VALUES ($1, $2, $3, $4)
        RETURNING id, user_id, agent_id, thread_id, status, created_at
        """,
        user_id,
        agent_id,
        thread_id,
        message_id,
    )


async def get_request(conn: asyncpg.Connection, request_id) -> asyncpg.Record | None:
    """按 id 取单条请求，供前端轮询/回显当前状态。"""
    return await conn.fetchrow(
        """
        SELECT id, user_id, agent_id, thread_id, status, created_at
        FROM agent_run_requests
        WHERE id = $1
        """,
        request_id,
    )


async def head_of_group_queue(
    conn: asyncpg.Connection, user_id: str, agent_id: str, thread_id: str
) -> asyncpg.Record | None:
    """取同组 (user, agent, thread) 里最早、仍在排队的请求。

    FIFO 串行的判据：只有当前请求 == 队头时才允许派发，保证同组一次只跑一个。
    """
    return await conn.fetchrow(
        """
        SELECT id, status, created_at
        FROM agent_run_requests
        WHERE user_id = $1 AND agent_id = $2 AND thread_id = $3
          AND status = 'queued'
        ORDER BY created_at
        LIMIT 1
        """,
        user_id,
        agent_id,
        thread_id,
    )


async def has_dispatched_in_group(
    conn: asyncpg.Connection, user_id: str, agent_id: str, thread_id: str
) -> bool:
    """判断同组是否已有「派发出去、还没收尾」的请求。

    FIFO 串行的另一半判据：组内只要有 dispatched 的请求，就说明有一个在跑，
    新请求必须继续排队，不能抢跑。
    """
    row = await conn.fetchrow(
        """
        SELECT 1
        FROM agent_run_requests
        WHERE user_id = $1 AND agent_id = $2 AND thread_id = $3
          AND status = 'dispatched'
        LIMIT 1
        """,
        user_id,
        agent_id,
        thread_id,
    )
    return row is not None


async def update_request_status(
    conn: asyncpg.Connection, request_id, status: str
) -> None:
    """推进请求状态（queued→dispatched→done/failed）。"""
    await conn.execute(
        "UPDATE agent_run_requests SET status = $2 WHERE id = $1",
        request_id,
        status,
    )


async def delete_requests_by_threads(conn: asyncpg.Connection, thread_ids: list) -> None:
    """删项目时清理其会话名下的请求（先删 run 再删这里）。"""
    await conn.execute(
        "DELETE FROM agent_run_requests WHERE thread_id = ANY($1::text[])",
        thread_ids,
    )
