"""SSE progress is best-effort; PostgreSQL is always the terminal-result authority."""
import asyncio
import contextlib
import json
import time
import redis.asyncio as aioredis
from app.events import request_channel
from app.repositories import messages, requests
from app.services.errors import public_error

RECONCILE_INTERVAL_SECONDS = 2


def _event(kind, data):
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _terminal(pool, request_id):
    async with pool.acquire() as conn:
        req = await requests.get_request(conn, request_id)
        if req is None:
            return [_event("done", {"status": "failed", "content": None, "error": "该请求已删除"})]
        if req["status"] not in ("done", "failed"):
            return None
        reply = await messages.get_assistant_reply(conn, request_id)
    events = []
    if reply:
        events.append(_event("sources", {"sources": json.loads(reply["sources"])}))
        for step in json.loads(reply["steps"]):
            events.append(_event("step", {"step": step}))
    events.append(_event("done", {"status": req["status"], "content": reply["content"] if reply else None,
                                 "error": public_error(req["error"]) if req["error"] else None}))
    return events


async def stream_request(pool, redis, request_id):
    pubsub = redis.pubsub()
    connected, seen = False, set()
    try:
        try:
            await pubsub.subscribe(request_channel(request_id))
            connected = True
            for raw in await redis.lrange(request_channel(request_id) + ":trace", 0, -1):
                payload = json.loads(raw)
                if payload["type"] in ("step", "sources"):
                    seen.add(json.dumps(payload, sort_keys=True))
                    yield _event(payload["type"], {payload["type"]: payload[payload["type"]]})
        except aioredis.RedisError:
            connected = False
        last_check = 0
        while True:
            now = time.monotonic()
            if now - last_check >= RECONCILE_INTERVAL_SECONDS:
                terminal = await _terminal(pool, request_id)
                last_check = now
                if terminal:
                    for event in terminal:
                        yield event
                    return
            msg = None
            if connected:
                try:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                except aioredis.RedisError:
                    connected = False
            else:
                await asyncio.sleep(1)
            if msg is None:
                yield ": keepalive\n\n"
                continue
            payload = json.loads(msg["data"])
            if payload["type"] == "done":
                last_check = 0  # Don't trust transient event content; reconcile committed result.
            elif payload["type"] == "token":
                # 增量不进 trace、不做去重：晚连的客户端本来就该靠 done 的完整正文对齐。
                yield _event("token", {"token": payload["token"]})
            elif payload["type"] in ("step", "sources"):
                identity = json.dumps(payload, sort_keys=True)
                if identity not in seen:
                    seen.add(identity)
                    yield _event(payload["type"], {payload["type"]: payload[payload["type"]]})
    finally:
        with contextlib.suppress(aioredis.RedisError):
            await pubsub.aclose()
