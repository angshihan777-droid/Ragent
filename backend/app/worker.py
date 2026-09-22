"""独立 worker 进程：从 Redis 取 run、抢租约执行、心跳续约、收尾拉下一个。

为什么单独一个进程：执行可能很慢（调 LLM），把它和 API 分开，
API 永远只做「落库即返回」保持轻快，worker 崩了也不影响用户继续提问。
"""
import asyncio
import socket
import uuid

import asyncpg
import redis.asyncio as aioredis

from app.agent.graph import stream_agent
from app.config import get_settings
from app.events import publish_done, publish_sources, publish_step, publish_token
from app.queue import QUEUE_KEY, enqueue_run
from app.repositories import messages, requests, runs
from app.services.scheduler import try_dispatch_group

# 心跳每 2s 续约一次；超过 10s 没心跳就判定 worker 失联、租约可被接管。
# 续约间隔远小于超时阈值，留足网络抖动余量，避免活着的 worker 被误判。
HEARTBEAT_INTERVAL_SECONDS = 2
LEASE_TIMEOUT_SECONDS = 10
# reaper 每 5s 扫一次过期租约，做崩溃恢复。
REAPER_INTERVAL_SECONDS = 5

# 每个 worker 进程一个唯一身份，写进 lease_owner，方便区分谁持有租约。
WORKER_ID = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


async def _heartbeat_loop(pool: asyncpg.Pool, run_id, lease_owner: str) -> None:
    """执行期间定时续约：只要本 worker 还活着，就周期性刷新 heartbeat_at。

    并发关键：心跳用独立连接、和执行并行跑。心跳一旦停更（进程崩溃/卡死），
    reaper 就能据此判定失联并接管这个 run。
    """
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        async with pool.acquire() as conn:
            await runs.heartbeat(conn, run_id, lease_owner)


async def _execute(
    pool: asyncpg.Pool,
    redis: aioredis.Redis,
    thread_id: str,
    request_id,
    question: str,
    project_id,
) -> str:
    """执行：运行 LangGraph，实时发布步骤/来源，引用检查后的回答落库并返回。

    question 来自 request 绑定的 message，不是「会话最后一条」——
    多条请求排队时，靠猜最后一条会串成同一个答案（已踩坑）。
    发布时序：回答通过图内校验后才收到正文事件；
    stream 正常跑完才落库，中途抛错则不写库、由上层收成 failed，
    避免把空回复或半截结果写进会话。
    回复绑定 request_id，SSE 客户端晚连时能从库里精确补读到本请求结果。
    """
    # pool 透传给图，检索节点用它查知识库(worker 有自己的连接池)
    parts: list[str] = []
    sources, steps = [], {}
    async for kind, data in stream_agent(
        question, pool, project_id, thread_id, request_id
    ):
        # step 是过程链条：某节点开始/完成，先于/伴随正文到达，推给右栏实时展示
        if kind == "step":
            steps[data["key"]] = data
            await publish_step(redis, request_id, data)
            continue
        # sources 先于正文到达：把本次检索命中的资料单独推一条，前端在资料卡片展示
        if kind == "sources":
            sources = data
            await publish_sources(redis, request_id, data)
            continue
        # token 保留现有 SSE 契约；目前正文在引用检查后一次发布
        parts.append(data)
        await publish_token(redis, request_id, data)
    reply = "".join(parts)
    async with pool.acquire() as conn:
        await messages.insert_message(
            conn, thread_id, "assistant", reply, request_id=request_id, sources=sources, steps=list(steps.values())
        )
    return reply


async def _handle_run(pool: asyncpg.Pool, redis: aioredis.Redis, run_id) -> None:
    """处理一个 run：抢租约 → 心跳并行执行 → 收尾 → 拉同组下一个。"""
    # 1) 抢租约。抢不到说明是重复投递（别的 worker 已在跑），直接丢弃。
    async with pool.acquire() as conn:
        claimed = await runs.claim_run(conn, run_id, WORKER_ID)
    if claimed is None:
        return

    # 2) 取分组信息（收尾要靠它拉同组下一个）
    async with pool.acquire() as conn:
        info = await runs.get_run_with_group(conn, run_id)
    request_id = info["request_id"]
    thread_id = info["thread_id"]
    user_id = info["user_id"]
    agent_id = info["agent_id"]
    question = info["question"]
    # 项目范围由服务端确定，模型不能自行选择
    project_id = info["project_id"]

    # 3) 心跳后台续约 + 执行并行；执行成败决定最终状态
    hb = asyncio.create_task(_heartbeat_loop(pool, run_id, WORKER_ID))
    status, error, reply = "done", None, None
    try:
        reply = await _execute(
            pool, redis, thread_id, request_id, question,
            project_id,
        )
    except Exception as e:  # 执行失败也要收尾，不能让 run 悬在 running
        status, error = "failed", str(e)
    finally:
        hb.cancel()  # 停止续约，避免收尾后还在刷心跳

    # 4) 收尾：单事务同时置 run 和 request 终态，避免只更新一半
    #    并在同事务里拉同组下一个（组空闲了才轮到它）
    async with pool.acquire() as conn:
        async with conn.transaction():
            await runs.finish_run(conn, run_id, status, error)
            await requests.update_request_status(conn, request_id, status)
            next_run_id = await try_dispatch_group(conn, user_id, agent_id, thread_id)
    # 时序关键：事务提交后再投递下一个，保证 worker 取到时库里已有该 run
    if next_run_id is not None:
        await enqueue_run(redis, next_run_id)
    # 事务已提交，此时推送 SSE 终态；订阅者收到时库里已是同一终态，late-join 补读一致
    await publish_done(redis, request_id, status, reply, error)


async def _reaper_loop(pool: asyncpg.Pool, redis: aioredis.Redis) -> None:
    """崩溃恢复：周期扫描心跳超时的 run，清租约并重投给活着的 worker。"""
    while True:
        await asyncio.sleep(REAPER_INTERVAL_SECONDS)
        async with pool.acquire() as conn:
            expired = await runs.reap_expired_leases(conn, LEASE_TIMEOUT_SECONDS)
        for run_id in expired:
            # 租约已清回 NULL，重投后其他 worker 能重新 claim_run 接管
            await enqueue_run(redis, run_id)


async def main() -> None:
    """worker 主循环：阻塞式取队列，边跑 reaper 边逐个处理 run。

    worker 自建 PG 池与 Redis 客户端，不复用 API 的 lifespan——它是独立进程。
    """
    settings = get_settings()
    pool = await asyncpg.create_pool(dsn=settings.database_url)
    redis = aioredis.from_url(settings.redis_url)
    reaper = asyncio.create_task(_reaper_loop(pool, redis))
    print(f"[worker {WORKER_ID}] started, waiting for runs...", flush=True)
    try:
        while True:
            # BRPOP 阻塞等队列；配合投递侧 LPUSH 天然 FIFO
            item = await redis.brpop(QUEUE_KEY)
            run_id = uuid.UUID(item[1].decode())
            await _handle_run(pool, redis, run_id)
    finally:
        reaper.cancel()
        await pool.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
