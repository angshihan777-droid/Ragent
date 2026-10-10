"""Leased worker: at-least-once execution, fenced/atomic result persistence."""
import asyncio
import contextlib
import logging
import socket
import uuid

import asyncpg
import redis.asyncio as aioredis

from app.agent.graph import stream_agent
from app.config import get_settings
from app.events import publish_done, publish_sources, publish_step, publish_token
from app.queue import QUEUE_KEY, enqueue_run
from app.repositories import messages, requests, runs
from app.services.errors import public_error
from app.services.scheduler import try_dispatch_group

HEARTBEAT_INTERVAL_SECONDS = 2
LEASE_TIMEOUT_SECONDS = 10
REAPER_INTERVAL_SECONDS = 5
# 同一个 run 最多执行几次：超过就判失败，防止"每次都让 worker 崩溃"的毒消息无限重投
MAX_ATTEMPTS = 3
# 单个 worker 进程同时跑几个 run：让不同会话真正并行（同会话仍由调度层保证串行）
WORKER_CONCURRENCY = 4
EXHAUSTED_ERROR = "本轮执行未完成：多次执行中断，已停止重试。"
WORKER_ID = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
log = logging.getLogger(__name__)


async def _notify(fn, *args):
    """Redis is delivery infrastructure, not the source of truth for completed work."""
    try:
        await fn(*args)
    except aioredis.RedisError:
        log.warning("Redis notification unavailable; database reconciliation will recover")


async def _heartbeat_loop(pool, run_id, owner):
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        async with pool.acquire() as conn:
            if not await runs.heartbeat(conn, run_id, owner):
                raise RuntimeError("lease lost")


async def _execute(pool, redis, thread_id, request_id, question, project_id, owner_id):
    parts, sources, steps, usage = [], [], {}, None
    buffered = []
    # owner_id 取自 run 所属请求的 user_id：worker 没有 HTTP 上下文，拿不到 Cookie，
    # 身份只能顺着 run → request 这条链子带下来，否则会退回「全局共用一份模型配置」。
    async for kind, data in stream_agent(question, pool, project_id, thread_id, request_id, owner_id):
        if kind == "token":
            # 实时增量只服务于"正在打字"的观感；发布失败不能连带把已经跑起来的回答打断，
            # 所以增量走 _notify（吞掉 Redis 故障），而终态在事务提交后照常发布。
            buffered.append(data)
            if sum(len(p) for p in buffered) >= 48:
                chunk, buffered[:] = "".join(buffered), []
                await _notify(publish_token, redis, request_id, chunk)
        elif kind == "step":
            steps[data["key"]] = data
            await _notify(publish_step, redis, request_id, data)
        elif kind == "sources":
            sources = data
            await _notify(publish_sources, redis, request_id, data)
        elif kind == "usage":
            usage = data
        else:
            # final：权威正文。Only publish after the fenced database commit.
            parts.append(data)
    if buffered:
        await _notify(publish_token, redis, request_id, "".join(buffered))
    return "".join(parts), sources, list(steps.values()), usage


async def finalize_run(pool, info, owner, status, error=None, result=None, usage=None):
    """One transaction commits result + terminal states + next FIFO dispatch.

    A replay or resumed stale worker cannot insert a second assistant reply.
    This does not guarantee exactly-once calls to an external model provider.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            if not await runs.finish_run(conn, info["run_id"], status, error, owner, usage):
                return False, None
            if result is not None and status == "done":
                reply, sources, steps = result[:3]
                await messages.insert_message(conn, info["thread_id"], "assistant", reply,
                    request_id=info["request_id"], sources=sources, steps=steps)
            await requests.update_request_status(conn, info["request_id"], status)
            next_id = await try_dispatch_group(conn, info["user_id"], info["agent_id"], info["thread_id"])
    return True, next_id


async def _handle_run(pool, redis, run_id):
    # An identity per attempt, not only per process (protects ABA lease reuse).
    owner = f"{WORKER_ID}:{uuid.uuid4().hex}"
    async with pool.acquire() as conn:
        if await runs.claim_run(conn, run_id, owner) is None:
            return
        info = await runs.get_run_with_group(conn, run_id)
    if info is None:  # A conversation can be deleted while a job is being claimed.
        return
    hb = asyncio.create_task(_heartbeat_loop(pool, run_id, owner))
    work = asyncio.create_task(_execute(pool, redis, info["thread_id"], info["request_id"],
                                       info["question"], info["project_id"], info["user_id"]))
    status, error, result = "done", None, None
    try:
        completed, _ = await asyncio.wait({hb, work}, return_when=asyncio.FIRST_COMPLETED)
        if hb in completed:
            hb.result()  # Lease loss/infrastructure failure: abandon, let reaper recover.
        usage = None
        try:
            result = work.result()
            usage = result[3] if len(result) > 3 else None
            if usage:
                log.info("Run usage request=%s %s", info["request_id"], usage)
        except Exception as exc:
            log.error("Execution failed request=%s exception=%s", info["request_id"], type(exc).__name__)
            status, error = "failed", public_error(exc)
        # Keep renewing until commit, including any wait for a DB connection.
        committed, next_id = await finalize_run(pool, info, owner, status, error, result, usage)
        if not committed:
            return
        if next_id is not None:
            await _notify(enqueue_run, redis, next_id)
        await _notify(publish_done, redis, info["request_id"], status, result[0] if result else None, error)
    finally:
        for task in (hb, work):
            task.cancel()
        await asyncio.gather(hb, work, return_exceptions=True)


async def _fail_exhausted(pool, redis, run_id, dead_owner):
    """已达重试上限：用原 owner 做 fencing 判失败，并照常放行同组下一个请求。"""
    async with pool.acquire() as conn:
        info = await runs.get_run_with_group(conn, run_id)
    if info is None:
        return
    # 与正常收尾走同一个事务：写失败状态 + 派发同组下一个，原 worker 若复活也写不回结果
    committed, next_id = await finalize_run(pool, info, dead_owner, "failed", EXHAUSTED_ERROR)
    if not committed:
        return
    log.warning("Run exhausted attempts request=%s", info["request_id"])
    if next_id is not None:
        await _notify(enqueue_run, redis, next_id)
    await _notify(publish_done, redis, info["request_id"], "failed", None, EXHAUSTED_ERROR)


async def recover_once(pool, redis):
    async with pool.acquire() as conn:
        exhausted = await runs.exhausted_runs(conn, LEASE_TIMEOUT_SECONDS, MAX_ATTEMPTS)
    for row in exhausted:
        await _fail_exhausted(pool, redis, row["id"], row["lease_owner"])
    async with pool.acquire() as conn:
        expired = await runs.reap_expired_leases(conn, LEASE_TIMEOUT_SECONDS, MAX_ATTEMPTS)
    for run_id in expired:
        await enqueue_run(redis, run_id)
    return expired


async def _reaper_loop(pool, redis):
    while True:
        await asyncio.sleep(REAPER_INTERVAL_SECONDS)
        try:
            await recover_once(pool, redis)
        except Exception as exc:
            log.warning("Recovery scan failed (%s); retrying next interval", type(exc).__name__)


async def main():
    settings = get_settings()
    pool = await asyncpg.create_pool(dsn=settings.database_url)
    redis = aioredis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=10)
    reaper = asyncio.create_task(_reaper_loop(pool, redis))
    # 有空位才去取任务：取到的任务一定马上能跑，不会领了租约却排队等空位
    slots = asyncio.Semaphore(WORKER_CONCURRENCY)
    running = set()

    async def run_one(run_id):
        try:
            await _handle_run(pool, redis, run_id)
        except Exception as exc:
            log.warning("Run failed outside execution (%s); lease recovery remains active", type(exc).__name__)
        finally:
            slots.release()

    print(f"[worker {WORKER_ID}] started, concurrency={WORKER_CONCURRENCY}", flush=True)
    try:
        while True:
            await slots.acquire()
            try:
                item = await redis.brpop(QUEUE_KEY, timeout=5)
                if not item:
                    slots.release()
                    continue
                task = asyncio.create_task(run_one(uuid.UUID(item[1].decode())))
                running.add(task)
                task.add_done_callback(running.discard)
            except Exception as exc:
                slots.release()
                log.warning("Worker iteration failed (%s); lease recovery remains active", type(exc).__name__)
                await asyncio.sleep(2)
    finally:
        reaper.cancel()
        for task in running:
            task.cancel()
        await asyncio.gather(reaper, *running, return_exceptions=True)
        await pool.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
