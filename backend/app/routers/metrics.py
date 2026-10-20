"""用量统计路由：按当前身份聚合 Token 与成功率。"""
import asyncpg
from fastapi import APIRouter, Depends, Query

from app.db import get_pool
from app.deps import get_owner_id
from app.schemas import MetricsSummaryOut
from app.services import metrics as metrics_service

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary", response_model=MetricsSummaryOut)
async def get_summary(
    days: int = Query(7, ge=1, le=365),
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """只统计当前身份自己的执行记录，不跨用户聚合。"""
    return await metrics_service.get_summary(pool, owner_id, days)
