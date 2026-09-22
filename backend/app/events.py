"""请求级实时事件：worker 把 token 增量和终态推到 Redis 频道，SSE 端订阅转发给前端。

面试点：Redis 只做「实时投递通道」，业务真相仍在 PostgreSQL。
即使订阅者错过某些 token 推送，也能从库里补读到完整终态，二者不冲突。
"""
import json

import redis.asyncio as aioredis


def request_channel(request_id) -> str:
    """一个请求一个频道，SSE 端点只订自己关心的那条，互不串扰。"""
    return f"ragent:request:{request_id}"


async def publish_token(redis: aioredis.Redis, request_id, token: str) -> None:
    """发布一个回复增量（token）。

    type=token 让 SSE 端区分「还在吐字」和「已收尾」两类消息；
    这些增量不落 Redis 持久层，晚连的客户端靠 publish_done 的完整内容兜底。
    """
    payload = json.dumps({"type": "token", "token": token})
    await redis.publish(request_channel(request_id), payload)


async def publish_sources(redis: aioredis.Redis, request_id, sources: list[dict]) -> None:
    """发布一条「本次检索命中的资料」事件，先于正文 token 推送。

    type=sources 让 SSE 端和前端把它与吐字/终态区分开：仅用于展示 RAG 检索了什么，
    不落库、不参与终态兜底，晚连的客户端丢了也不影响最终答案。
    """
    payload = json.dumps({"type": "sources", "sources": sources})
    await redis.publish(request_channel(request_id), payload)


async def publish_step(redis: aioredis.Redis, request_id, step: dict) -> None:
    """发布一条「过程链条」步骤事件：某节点开始(running)或完成(done)。

    type=step 让 SSE 端和前端把它与检索命中/吐字/终态区分开：仅用于右栏实时展示
    执行进行到哪一步，不落库、不参与终态兜底，晚连的客户端丢了也不影响最终答案。
    """
    payload = json.dumps({"type": "step", "step": step})
    await redis.publish(request_channel(request_id), payload)


async def publish_done(
    redis: aioredis.Redis, request_id, status: str, content: str | None, error: str | None
) -> None:
    """发布一条请求终态事件（done/failed），带完整内容做兜底。

    时序关键：调用方必须在 PG 事务 commit 之后再发，
    保证订阅者收到推送时，库里已是同一终态，late-join 补读也一致。
    """
    payload = json.dumps(
        {
            "type": "done",
            "request_id": str(request_id),
            "status": status,
            "content": content,
            "error": error,
        }
    )
    await redis.publish(request_channel(request_id), payload)
