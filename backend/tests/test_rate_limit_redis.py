"""Redis 限流集成测试：设置 TEST_REDIS_URL 才运行（CI 的 retrieval-eval job）。"""
import asyncio
import os
import time
import uuid

import pytest
import redis.asyncio as aioredis

from app.guards.rate_limit import RedisSlidingWindowLimiter

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_REDIS_URL"),
    reason="需要 TEST_REDIS_URL 指向可用的 Redis",
)


def test_redis_limiter_blocks_then_expires():
    async def scenario():
        redis = aioredis.from_url(os.environ["TEST_REDIS_URL"])
        key = "test-" + uuid.uuid4().hex
        limiter = RedisSlidingWindowLimiter(limit=2, window_seconds=0.5)
        try:
            assert (await limiter.check(redis, key)).allowed
            assert (await limiter.check(redis, key)).allowed
            denied = await limiter.check(redis, key)
            assert denied.allowed is False
            assert denied.retry_after >= 1
            await asyncio.sleep(0.6)
            assert (await limiter.check(redis, key)).allowed
        finally:
            await redis.delete("ragent:ratelimit:" + key)
            await redis.aclose()

    asyncio.run(scenario())
