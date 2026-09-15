"""请求接入的用例流程：落库即返回 ID，并在同组空闲时立刻派发队头。

放在 service 层是因为它编排了「查会话绑定的 Agent + 写消息 + 写请求 + 派发决策 + 投递」多步，
属于业务流程，而不是单条 SQL；路由只管收发，SQL 只管读写。
"""
import asyncpg
import redis.asyncio as aioredis

from app.config import FIXED_USER_ID
from app.queue import enqueue_run
from app.repositories import messages, requests, threads
from app.services.scheduler import try_dispatch_group


async def create_request(
    pool: asyncpg.Pool, redis: aioredis.Redis, thread_id: str, content: str
) -> dict | None:
    """落一次提问并尝试派发：同事务写消息+写请求+决策，commit 后再投递。

    先查会话绑定的 Agent：调度键的 agent 段来自 threads.agent_id，不再写死，
    不同 Agent 因此得到不同的 (user, agent, thread) 三元组，天然独立排队。
    会话不存在返回 None，由路由收成 404。

    时序关键：enqueue 必须在事务 commit 之后。若先投递再 commit，
    worker 可能先取到消息，却在库里查不到刚建的 run。
    """
    async with pool.acquire() as conn:
        thread = await threads.get_thread(conn, thread_id)
        if thread is None:
            return None
        agent_id = str(thread["agent_id"])
        # 单事务：消息、请求、派发决策同生共死，避免半截状态
        async with conn.transaction():
            msg = await messages.insert_message(conn, thread_id, "user", content)
            # 请求绑定刚落库的这条 user 消息，worker 据此取本次要回答的问题
            req = await requests.insert_request(
                conn, FIXED_USER_ID, agent_id, thread_id, msg["id"]
            )
            # 同组空闲则放行队头，拿到待投递的 run_id（可能是本请求，也可能不是）
            run_id = await try_dispatch_group(
                conn, FIXED_USER_ID, agent_id, thread_id
            )
    # 事务已提交，run 一定已在库里，此时投递才安全
    if run_id is not None:
        await enqueue_run(redis, run_id)
    return {
        "request_id": req["id"],
        "message_id": msg["id"],
        "status": req["status"],
    }


async def get_request(pool: asyncpg.Pool, request_id) -> dict | None:
    """查询单条请求当前状态，供前端轮询。"""
    async with pool.acquire() as conn:
        row = await requests.get_request(conn, request_id)
    if row is None:
        return None
    return {
        "id": row["id"],
        "thread_id": row["thread_id"],
        "status": row["status"],
        "created_at": row["created_at"],
    }
