"""agent_runs 表的读写：系统视角的「执行账本」。

一次执行的生命周期：create_run 抢占 → heartbeat 续约 → finish_run 收尾。
函数只写单条 SQL，租约是否过期、能否接管由上层调度判断。
"""
import json

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
    """worker 抢占租约：只有 pending 的 run 能被抢到，抢到即转 running，返回 None 表示抢占失败。

    并发关键：WHERE status = 'pending' 让抢占是原子的——
    Redis 若重复投递同一条消息、或 reaper 重投了同一条，只有第一个 worker 能把它从
    pending 翻成 running，其余拿到 None 直接丢弃，不会出现两个 worker 跑同一个 run。
    reaper 接管孤儿时会把 run 打回 pending，所以这里用 status 而非 lease_owner 作为闸门。
    """
    return await conn.fetchrow(
        """
        UPDATE agent_runs
        SET status = 'running', lease_owner = $2, heartbeat_at = now(), attempts = attempts + 1
        WHERE id = $1 AND status = 'pending'
        RETURNING id, request_id, status, attempts
        """,
        run_id,
        lease_owner,
    )


async def heartbeat(conn: asyncpg.Connection, run_id, lease_owner: str) -> bool:
    """worker 定时续约：只有持租者能刷新心跳，避免误续别人的 run。

    一条 UPDATE ... RETURNING 同时完成「续约」和「确认租约还在」，
    返回 False 表示租约已被接管或 run 已结束。
    """
    row = await conn.fetchrow(
        """
        UPDATE agent_runs
        SET heartbeat_at = now()
        WHERE id = $1 AND lease_owner = $2 AND status = 'running'
        RETURNING id
        """,
        run_id,
        lease_owner,
    )
    return row is not None


async def finish_run(conn, run_id, status, error, lease_owner, usage=None) -> bool:
    """Fence the commit with the unique attempt owner; callers must use a transaction."""
    row = await conn.fetchrow("""
        UPDATE agent_runs SET status=$2, error=$3, usage=COALESCE($5::jsonb, usage)
        WHERE id=$1 AND status='running' AND lease_owner=$4
        RETURNING id
    """, run_id, status, error, lease_owner, json.dumps(usage) if usage is not None else None)
    return row is not None


async def get_run_with_group(
    conn: asyncpg.Connection, run_id
) -> asyncpg.Record | None:
    """取 run 及其所属请求的分组信息 (user, agent, thread)。

    worker 收尾后要「拉同组下一个」，必须先知道这个 run 属于哪一组，
    所以联表把请求的分组字段一起取出来；同时带出本请求绑定的 user 消息内容，
    让执行只回答「这一条」的问题，不靠猜会话里最后一条。
    联会话取得服务端限定的项目范围。
    """
    return await conn.fetchrow(
        """
        SELECT r.id AS run_id, r.request_id, r.status AS run_status,
               q.user_id, q.agent_id, q.thread_id,
               m.content AS question,
               t.project_id
        FROM agent_runs r
        JOIN agent_run_requests q ON q.id = r.request_id
        JOIN messages m ON m.id = q.message_id
        JOIN threads t ON t.id::text = q.thread_id
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


async def get_usage_by_request(conn: asyncpg.Connection, request_id) -> dict | None:
    """取一次请求最近一条 run 的 usage，供 SSE 终态把本轮 Token 用量带回前端。

    重试会产生多条 run；成功收尾的那条才带 usage，按时间倒序取第一条即可。
    """
    row = await conn.fetchrow(
        """
        SELECT usage FROM agent_runs
        WHERE request_id = $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        request_id,
    )
    return row["usage"] if row else None

async def exhausted_runs(conn: asyncpg.Connection, lease_timeout_seconds: int, max_attempts: int) -> list:
    """心跳已停、且已执行满 max_attempts 次的 run：不再重投，交给上层判失败。

    毒消息防护：某个请求每次都让 worker 崩溃时，无限重投会让同组后面的请求永远排不上。
    返回 run_id 和当时的 lease_owner，上层用 lease_owner 做 fencing 收尾。
    """
    return await conn.fetch(
        """
        SELECT id, lease_owner FROM agent_runs
        WHERE status = 'running' AND lease_owner IS NOT NULL
          AND heartbeat_at < now() - make_interval(secs => $1)
          AND attempts >= $2
        """,
        lease_timeout_seconds,
        max_attempts,
    )


async def reap_expired_leases(
    conn: asyncpg.Connection, lease_timeout_seconds: int, max_attempts: int = 1_000_000
) -> list:
    """接管两类孤儿 run：打回 pending 并返回需重投的 run_id 列表。

    崩溃恢复关键：一次捞两种失联情形，都靠"超时"判定并原子打回 pending，
    让 claim_run 能重新抢占（claim 以 status='pending' 为闸门）：
      1) running 但心跳停更超过 lease_timeout —— worker 执行中崩了/卡死；
      2) pending 但建出来超过 lease_timeout 仍没人认领 —— "先 commit 后 enqueue"
         在 enqueue 处失败(Redis 抖动/worker 全挂)，这条 run 从没进过队列。
    WHERE 内再次校验超时，避免误接管刚续约或刚建正要被认领的 run；
    重投是幂等的：即便这条其实已被某 worker 取走，claim_run 的原子闸门会让重复投递落空。
    """
    rows = await conn.fetch(
        """
        UPDATE agent_runs
        SET status = 'pending', lease_owner = NULL, heartbeat_at = now()
        WHERE (
                status = 'running'
                AND lease_owner IS NOT NULL
                AND heartbeat_at < now() - make_interval(secs => $1)
                AND attempts < $2
              )
           OR (
                status = 'pending'
                -- 回收时把 heartbeat_at 记成"最近一次投递时间"：同一个 run 每个超时窗口最多重投一次，
                -- 不会在 worker 忙时每轮扫描都往队列里再塞一份
                AND COALESCE(heartbeat_at, created_at) < now() - make_interval(secs => $1)
              )
        RETURNING id
        """,
        lease_timeout_seconds,
        max_attempts,
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
