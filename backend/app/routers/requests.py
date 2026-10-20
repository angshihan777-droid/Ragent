"""请求接入路由：保持薄，只做参数收发与状态码，业务在 service。"""
import logging
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.db import get_pool, get_redis
from app.deps import assert_owned_thread, get_owner_id, require_owned_request
from app.guards.prompt_injection import detect_injection
from app.guards.rate_limit import limit_requests
from app.schemas import CreateRequestIn, CreateRequestOut, RequestOut
from app.services import audit
from app.services import requests as request_service
from app.services import sse as sse_service

router = APIRouter(prefix="/requests", tags=["requests"])
log = logging.getLogger(__name__)


@router.post("", response_model=CreateRequestOut, status_code=201)
async def create_request(
    body: CreateRequestIn,
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis),
    _rate_limit: None = Depends(limit_requests),
):
    """收到提问就落库并立刻返回 ID；同组空闲则顺带派发队头，不阻塞等待执行。

    会话 id 在 body 里，路径依赖拿不到，所以在这里显式校验一次归属：
    不校验的话，别人只要知道会话 id 就能往你的对话里塞消息。
    """
    verdict = detect_injection(body.content)
    if verdict.blocked:
        # 只记规则编号与长度，不把攻击载荷写进日志。
        log.warning("Blocked prompt injection rule=%s length=%d", verdict.rule_id, verdict.text_length)
        await audit.record(
            pool, owner_id, "prompt_injection_blocked",
            rule_id=verdict.rule_id, length=verdict.text_length,
        )
        raise HTTPException(
            status_code=400,
            detail="请求包含不被允许的指令，请改为正常提问。",
        )

    await assert_owned_thread(pool, body.thread_id, owner_id)
    result = await request_service.create_request(
        pool, redis, owner_id, body.thread_id, body.content
    )
    if result is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return result


@router.get("/{request_id}", response_model=RequestOut)
async def get_request(
    request_id: UUID = Depends(require_owned_request),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """查询请求当前状态；不存在或不归自己都返回 404 而不是空对象。"""
    row = await request_service.get_request(pool, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="request not found")
    return row


@router.get("/{request_id}/stream")
async def stream_request(
    request_id: UUID = Depends(require_owned_request),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis),
):
    """SSE 长连接：实时推送本请求的执行结果，替代前端轮询。

    text/event-stream + 关缓存；生成器内部「先订阅再查库」消灭连接窗口漏推。

    ⚠️ require_owned_request 不能省：这个端点看上去「只订阅 Redis 频道、没碰业务表」，
    但流里推的就是完整回答正文——不验归属，知道 request_id 就能偷听别人的对话。
    校验发生在依赖阶段，即返回 StreamingResponse 之前，越权连接根本建不起来。
    """
    return StreamingResponse(
        sse_service.stream_request(pool, redis, request_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
