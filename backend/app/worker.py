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
from app.events import publish_done, publish_sources, publish_step
from app.queue import QUEUE_KEY, enqueue_run
from app.repositories import messages, requests, runs
from app.services.errors import public_error
from app.services.scheduler import try_dispatch_group

HEARTBEAT_INTERVAL_SECONDS = 2
LEASE_TIMEOUT_SECONDS = 10
REAPER_INTERVAL_SECONDS = 5
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
            await runs.heartbeat(conn, run_id, owner)
            row = await runs.get_run(conn, run_id)
            if not row or row["status"] != "running" or row["lease_owner"] != owner:
                raise RuntimeError("lease lost")


async def _execute(pool, redis, thread_id, request_id, question, project_id):
    parts, sources, steps = [], [], {}
    async for kind, data in stream_agent(question, pool, project_id, thread_id, request_id):
        if kind == "step":
            steps[data["key"]] = data
            await _notify(publish_step, redis, request_id, data)
        elif kind == "sources":
            sources = data
            await _notify(publish_sources, redis, request_id, data)
        else:
            # Only publish authoritative text after the fenced database commit.
            parts.append(data)
    return "".join(parts), sources, list(steps.values())


async def finalize_run(pool, info, owner, status, error=None, result=None):
    """One transaction commits result + terminal states + next FIFO dispatch.

    A replay or resumed stale worker cannot insert a second assistant reply.
    This does not guarantee exactly-once calls to an external model provider.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            if not await runs.finish_run(conn, info["run_id"], status, error, owner):
                return False, None
            if result is not None and status == "done":
                reply, sources, steps = result
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
                                       info["question"], info["project_id"]))
    status, error, result = "done", None, None
    try:
        completed, _ = await asyncio.wait({hb, work}, return_when=asyncio.FIRST_COMPLETED)
        if hb in completed:
            hb.result()  # Lease loss/infrastructure failure: abandon, let reaper recover.
        try:
            result = work.result()
        except Exception as exc:
            log.error("Execution failed request=%s exception=%s", info["request_id"], type(exc).__name__)
            status, error = "failed", public_error(exc)
        # Keep renewing until commit, including any wait for a DB connection.
        committed, next_id = await finalize_run(pool, info, owner, status, error, result)
        if not committed:
            return
        if next_id is not None:
            await _notify(enqueue_run, redis, next_id)
        await _notify(publish_done, redis, info["request_id"], status, result[0] if result else None, error)
    finally:
        for task in (hb, work):
            task.cancel()
        await asyncio.gather(hb, work, return_exceptions=True)


async def recover_once(pool, redis):
    async with pool.acquire() as conn:
        expired = await runs.reap_expired_leases(conn, LEASE_TIMEOUT_SECONDS)
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
    print(f"[worker {WORKER_ID}] started", flush=True)
    try:
        while True:
            try:
                item = await redis.brpop(QUEUE_KEY, timeout=5)
                if item:
                    await _handle_run(pool, redis, uuid.UUID(item[1].decode()))
            except Exception as exc:
                log.warning("Worker iteration failed (%s); lease recovery remains active", type(exc).__name__)
                await asyncio.sleep(2)
    finally:
        reaper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reaper
        await pool.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
