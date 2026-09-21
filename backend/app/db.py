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
    # 启动即建表：schema.sql 全用 IF NOT EXISTS，重复启动安全
    async with pg_pool.acquire() as conn:
        await conn.execute(_SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        yield
    finally:
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
