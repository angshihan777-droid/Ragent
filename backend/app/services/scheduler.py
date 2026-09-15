"""FIFO 派发决策：同组 (user, agent, thread) 一次只放行一个请求。

面试点：把「谁能跑」这件事收敛成一个函数 try_dispatch_group。
不管是新请求进来，还是上一个 run 跑完想拉下一个，都调用它，逻辑只有一处。
"""
import asyncpg

from app.repositories import requests, runs


# 用组标识算一个稳定的 64 位整数，喂给 PG 的事务级 advisory 锁。
# 目的：让「同一组」的并发派发决策互斥，跨组互不影响。
def _group_lock_key(user_id: str, agent_id: str, thread_id: str) -> int:
    return hash((user_id, agent_id, thread_id)) % (2**63)


async def try_dispatch_group(
    conn: asyncpg.Connection,
    user_id: str,
    agent_id: str,
    thread_id: str,
):
    """在当前事务里尝试为该组放行一个请求，返回新建的 run_id 或 None。

    并发关键：先取组级事务锁，保证同组两个请求同时进来时，
    派发判定串行执行、不会都被放行。锁随事务结束自动释放。

    时序关键：本函数只负责「建 run + 置 dispatched」，
    真正的 enqueue 必须由调用方在事务 commit 之后再做。
    """
    # 1) 组级互斥：同组决策排队，跨组并行
    await conn.execute(
        "SELECT pg_advisory_xact_lock($1)",
        _group_lock_key(user_id, agent_id, thread_id),
    )
    # 2) 组里已经有人在跑（dispatched 未收尾）→ 让新请求继续排队
    if await requests.has_dispatched_in_group(conn, user_id, agent_id, thread_id):
        return None
    # 3) 组空闲 → 取最早的排队请求作为队头放行
    head = await requests.head_of_group_queue(conn, user_id, agent_id, thread_id)
    if head is None:
        return None
    run = await runs.create_run(conn, head["id"])
    await requests.update_request_status(conn, head["id"], "dispatched")
    return run["id"]
