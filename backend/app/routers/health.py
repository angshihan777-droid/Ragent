"""健康检查路由：区分进程存活与依赖就绪。

/health 只表达进程 liveness；/ready 真正探测 PG 与 Redis，
未就绪时返回 503 并指出是哪个依赖不通，绝不假装成功。
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db import check_postgres, check_redis

router = APIRouter()


@router.get("/health")
async def health():
    """进程活着就返回 200，不探测任何外部依赖。"""
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """PG 和 Redis 都通才 200；任一不通返回 503 并标明。"""
    pg_ok = await check_postgres()
    redis_ok = await check_redis()
    if pg_ok and redis_ok:
        return {"status": "ok", "postgres": True, "redis": True}
    # 依赖未就绪：显式 503，暴露具体哪个没通，便于排查
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "postgres": pg_ok, "redis": redis_ok},
    )
