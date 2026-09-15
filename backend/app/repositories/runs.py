"""agent_runs 表的读写：系统视角的「执行账本」。

一次执行的生命周期：create_run 抢占 → heartbeat 续约 → finish_run 收尾。
函数只写单条 SQL，租约是否过期、能否接管由上层调度判断。
"""
import asyncpg


async def create_run(conn: asyncpg.Connection, request_id) -> asyncpg.Record:
    """请求排到队头时创建 run，但先不设租约。

    面试点：派发者（调度）只负责「建 run + 投递」，真正的执行权（lease_owner
    与 heartbeat）由 worker 抢占时再写，二者职责分离。
    """
    return await conn.fetchrow(
        """
        INSERT INTO agent_runs (request_id)
        VALUES ($1)
        RETURNING id, request_id, status, lease_owner, heartbeat_at, created_at
        """,
        request_id,
    )


async def claim_run(
    conn: asyncpg.Connection, run_id, lease_owner: str
) -> asyncpg.Record | None:
    """worker 抢占租约：只有还没人认领的 run 能被抢到，返回 None 表示抢占失败。

    并发关键：WHERE lease_owner IS NULL 让抢占是原子的——
    Redis 若重复投递同一条消息，只有第一个 worker 能抢到，其余拿到 None 直接丢弃，
    不会出现两个 worker 跑同一个 run。
    """
    return await conn.fetchrow(
        """
        UPDATE agent_runs
        SET lease_owner = $2, heartbeat_at = now()
        WHERE id = $1 AND lease_owner IS NULL
        RETURNING id, request_id, status
        """,
        run_id,
        lease_owner,
    )


async def heartbeat(conn: asyncpg.Connection, run_id, lease_owner: str) -> None:
    """worker 定时续约：只有持租者能刷新心跳，避免误续别人的 run。"""
    await conn.execute(
        """
        UPDATE agent_runs
        SET heartbeat_at = now()
        WHERE id = $1 AND lease_owner = $2
        """,
        run_id,
        lease_owner,
    )


async def finish_run(
    conn: asyncpg.Connection, run_id, status: str, error: str | None
) -> None:
    """收尾：把 run 置为终态 done/failed，失败时带上错误原因。"""
    await conn.execute(
        "UPDATE agent_runs SET status = $2, error = $3 WHERE id = $1",
        run_id,
        status,
        error,
    )


async def get_run_with_group(
    conn: asyncpg.Connection, run_id
) -> asyncpg.Record | None:
    """取 run 及其所属请求的分组信息 (user, agent, thread)。

    worker 收尾后要「拉同组下一个」，必须先知道这个 run 属于哪一组，
    所以联表把请求的分组字段一起取出来；同时带出本请求绑定的 user 消息内容，
    让执行只回答「这一条」的问题，不靠猜会话里最后一条。
    同时联 threads/agents 带出本会话 Agent 的 system_prompt/use_rag 和 project_id，
    供执行时决定「是否检索、检索哪个项目的资料、注入什么人设」。
    """
    return await conn.fetchrow(
        """
        SELECT r.id AS run_id, r.request_id, r.status AS run_status,
               q.user_id, q.agent_id, q.thread_id,
               m.content AS question,
               t.project_id, a.system_prompt, a.use_rag
        FROM agent_runs r
        JOIN agent_run_requests q ON q.id = r.request_id
        JOIN messages m ON m.id = q.message_id
        JOIN threads t ON t.id::text = q.thread_id
        JOIN agents a ON a.id = t.agent_id
        WHERE r.id = $1
        """,
        run_id,
    )


async def get_run(conn: asyncpg.Connection, run_id) -> asyncpg.Record | None:
    """按 id 取单条 run，用于查询执行状态。"""
    return await conn.fetchrow(
        """
        SELECT id, request_id, status, lease_owner, heartbeat_at, error, created_at
        FROM agent_runs
        WHERE id = $1
        """,
        run_id,
    )

async def reap_expired_leases(
    conn: asyncpg.Connection, lease_timeout_seconds: int
) -> list:
    """接管失联 worker 的 run：清空心跳超时者的租约，返回需重投的 run_id 列表。

    崩溃恢复关键：worker 崩了心跳就停更，超过 lease_timeout 即判定失联。
    这里原子地把过期租约清回 NULL（WHERE 再次校验超时，避免误接管刚续约的），
    清成功的才返回，交给上层重新投递让活着的 worker 接管。
    """
    rows = await conn.fetch(
        """
        UPDATE agent_runs
        SET lease_owner = NULL
        WHERE status = 'running'
          AND lease_owner IS NOT NULL
          AND heartbeat_at < now() - make_interval(secs => $1)
        RETURNING id
        """,
        lease_timeout_seconds,
    )
    return [r["id"] for r in rows]


async def delete_runs_by_threads(conn: asyncpg.Connection, thread_ids: list) -> None:
    """删项目时清理其会话名下的 run（先于删请求，避免外键悬挂）。"""
    await conn.execute(
        """
        DELETE FROM agent_runs
        WHERE request_id IN (
            SELECT id FROM agent_run_requests WHERE thread_id = ANY($1::text[])
        )
        """,
        thread_ids,
    )
