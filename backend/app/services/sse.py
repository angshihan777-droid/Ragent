"""SSE 用例流程：把一个请求的执行结果实时推给前端，不用轮询。

关键竞态：POST 返回后到 SSE 连上之间，run 可能已经跑完。
pub/sub 不持久化，若先查库再订阅就会漏掉这段窗口的推送、然后一直干等。
所以顺序固定为「先订阅、再查库」：订阅在前保证不漏；
若查库已是终态直接补发并结束，否则挂在频道上等 worker 推。
"""
import json

import asyncpg
import redis.asyncio as aioredis

from app.events import request_channel
from app.repositories import messages, requests

# 每 15s 发一个 SSE 注释行做心跳，防止中间代理把空闲长连接掐断
KEEPALIVE_INTERVAL_SECONDS = 15


def _format_done(status: str, content: str | None, error: str | None) -> str:
    """按 SSE 协议格式化一条终态事件（done），带完整内容供前端最终落地。"""
    data = json.dumps({"status": status, "content": content, "error": error})
    return f"event: done\ndata: {data}\n\n"


def _format_token(token: str) -> str:
    """格式化一条回复增量事件（token），前端收到即实时追加。"""
    data = json.dumps({"token": token})
    return f"event: token\ndata: {data}\n\n"


def _format_sources(sources: list) -> str:
    """格式化一条检索命中事件（sources），前端在答案上方展示「检索到了什么」。"""
    data = json.dumps({"sources": sources})
    return f"event: sources\ndata: {data}\n\n"


def _format_step(step: dict) -> str:
    """格式化一条过程链条事件（step），前端据此在右栏更新步骤进度与转圈。"""
    data = json.dumps({"step": step})
    return f"event: step\ndata: {data}\n\n"


async def stream_request(
    pool: asyncpg.Pool, redis: aioredis.Redis, request_id
):
    """产出 SSE 事件流：命中终态就推一条 done 并结束，否则等 worker 推送。"""
    pubsub = redis.pubsub()
    # 先订阅：确保订阅早于下面的查库，堵住「查完到订阅之间 run 跑完」的漏推窗口
    await pubsub.subscribe(request_channel(request_id))
    try:
        seen = set()
        cached = await redis.lrange(request_channel(request_id) + ":trace", 0, -1)
        for raw in cached:
            payload = json.loads(raw)
            seen.add(json.dumps(payload, sort_keys=True))
            if payload["type"] == "step":
                yield _format_step(payload["step"])
            elif payload["type"] == "sources":
                yield _format_sources(payload["sources"])
        # 再查库：若已终态（含 SSE 连上前就跑完的情况），直接补发结果并结束
        async with pool.acquire() as conn:
            req = await requests.get_request(conn, request_id)
            if req is None:
                yield _format_done("failed", None, "request not found")
                return
            if req["status"] in ("done", "failed"):
                reply = await messages.get_assistant_reply(conn, request_id)
                content = reply["content"] if reply else None
                if reply:
                    sources = json.loads(reply["sources"])
                    if json.dumps({"type": "sources", "sources": sources}, sort_keys=True) not in seen:
                        yield _format_sources(sources)
                    for step in json.loads(reply["steps"]):
                        if json.dumps({"type": "step", "step": step}, sort_keys=True) not in seen:
                            yield _format_step(step)
                yield _format_done(req["status"], content, req.get("error"))
                return

        # 未终态：挂在频道上等 worker 收尾推送；超时则发心跳保活
        while True:
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=KEEPALIVE_INTERVAL_SECONDS
            )
            if msg is None:
                yield ": keepalive\n\n"  # SSE 注释行，仅保活不触发前端事件
                continue
            payload = json.loads(msg["data"])
            if payload["type"] in ("step", "sources"):
                identity = json.dumps(payload, sort_keys=True)
                if identity in seen:
                    continue
                seen.add(identity)
            # sources 是检索命中，先于正文到达；token 是回复增量：两者都边收边转发、不结束
            if payload["type"] == "step":
                yield _format_step(payload["step"])
                continue
            if payload["type"] == "sources":
                yield _format_sources(payload["sources"])
                continue
            if payload["type"] == "token":
                yield _format_token(payload["token"])
                continue
            yield _format_done(payload["status"], payload.get("content"), payload.get("error"))
            return
    finally:
        # 客户端断开或正常结束都要退订，避免连接与订阅泄漏
        await pubsub.unsubscribe(request_channel(request_id))
        await pubsub.aclose()
