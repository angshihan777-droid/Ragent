"""PG 与 Redis 连接的生命周期管理。

连接池在应用启动时建立、关闭时释放；启动时执行一次建表（幂等），
之后只提供连接与最小连通性探测。
"""
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI

from app.config import get_settings

# worker 存活心跳：每个 worker 进程每 5 秒刷新一次，15 秒没刷新即视为掉线。
# 放 Redis 而不是 PG：心跳是易失状态，不值得每次写库。
WORKER_HEARTBEAT_PREFIX = "ragent:worker:"
WORKER_HEARTBEAT_TTL_SECONDS = 15

# 进程级共享的连接池/客户端，由 lifespan 负责建立和释放
pg_pool: asyncpg.Pool | None = None
redis_client: aioredis.Redis | None = None

# 建表 SQL 与本文件同级，随镜像一起打包
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时建立连接并建表，关闭时释放，保证资源不泄漏。"""
    global pg_pool, redis_client
    settings = get_settings()
    pg_pool = await asyncpg.create_pool(dsn=settings.database_url)
    redis_client = aioredis.from_url(settings.redis_url)
    # 启动执行幂等建表与兼容迁移
    async with pg_pool.acquire() as conn:
        await conn.execute(_SCHEMA_PATH.read_text(encoding="utf-8"))
    # 图执行状态持久化：同一请求重试时能从最后一个 checkpoint 续跑。
    from app.agent import graph as agent_graph
    try:
        await agent_graph.init_checkpointer(settings.database_url)
        yield
    finally:
        await agent_graph.close_checkpointer()
        if pg_pool is not None:
            await pg_pool.close()
        if redis_client is not None:
            await redis_client.aclose()


def get_pool() -> asyncpg.Pool:
    """返回进程级连接池，供路由通过依赖注入拿到它。

    未初始化即失败（预设条件不成立就显式报错），不静默返回 None。
    """
    if pg_pool is None:
        raise RuntimeError("PG 连接池尚未初始化")
    return pg_pool


def get_redis() -> aioredis.Redis:
    """返回进程级 Redis 客户端，供路由通过依赖注入拿到它。

    未初始化即失败，不静默返回 None。
    """
    if redis_client is None:
        raise RuntimeError("Redis 客户端尚未初始化")
    return redis_client


async def check_postgres() -> bool:
    """探测 PG 是否可用：能执行 SELECT 1 才算通。"""
    if pg_pool is None:
        return False
    try:
        async with pg_pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception:
        return False


async def check_redis() -> bool:
    """探测 Redis 是否可用：PING 通才算通。"""
    if redis_client is None:
        return False
    try:
        return bool(await redis_client.ping())
    except Exception:
        return False


async def check_worker() -> bool:
    """是否有 worker 在刷新心跳；没有就说明请求会一直排队。"""
    if redis_client is None:
        return False
    try:
        async for _ in redis_client.scan_iter(match=WORKER_HEARTBEAT_PREFIX + "*", count=100):
            return True
        return False
    except Exception:
        return False


async def queue_snapshot() -> dict:
    """返回执行队列的积压情况；查不到时用 None，表示「未知」而不是 0。"""
    empty = {"pending": None, "running": None, "oldest_pending_seconds": None}
    if pg_pool is None:
        return empty
    try:
        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    count(*) FILTER (WHERE status = 'pending') AS pending,
                    count(*) FILTER (WHERE status = 'running') AS running,
                    EXTRACT(EPOCH FROM (
                        now() - min(created_at) FILTER (WHERE status = 'pending')
                    )) AS oldest_pending_seconds
                FROM agent_runs
                """
            )
    except Exception:
        return empty
    oldest = row["oldest_pending_seconds"]
    return {
        "pending": int(row["pending"] or 0),
        "running": int(row["running"] or 0),
        "oldest_pending_seconds": round(float(oldest), 1) if oldest is not None else None,
    }
