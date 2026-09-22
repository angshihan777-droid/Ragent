"""请求接入路由：保持薄，只做参数收发与状态码，业务在 service。"""
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.db import get_pool, get_redis
from app.schemas import CreateRequestIn, CreateRequestOut, RequestOut
from app.services import requests as request_service
from app.services import sse as sse_service

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", response_model=CreateRequestOut, status_code=201)
async def create_request(
    body: CreateRequestIn,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis),
):
    """收到提问就落库并立刻返回 ID；同组空闲则顺带派发队头，不阻塞等待执行。"""
    result = await request_service.create_request(
        pool, redis, body.thread_id, body.content
    )
    if result is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return result


@router.get("/{request_id}", response_model=RequestOut)
async def get_request(request_id: UUID, pool: asyncpg.Pool = Depends(get_pool)):
    """查询请求当前状态；不存在返回 404 而不是空对象。"""
    row = await request_service.get_request(pool, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="request not found")
    return row


@router.get("/{request_id}/stream")
async def stream_request(
    request_id: UUID,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis),
):
    """SSE 长连接：实时推送本请求的执行结果，替代前端轮询。

    text/event-stream + 关缓存；生成器内部「先订阅再查库」消灭连接窗口漏推。
    """
    return StreamingResponse(
        sse_service.stream_request(pool, redis, request_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
