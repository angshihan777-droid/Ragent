"""进程内滑动窗口限流。

单实例部署够用；多副本时各进程各算各的，需要换成 Redis 计数器。
键用 owner_id 而不是纯 IP：身份已经由依赖解析出来，按身份限流不会误伤同一出口 NAT 后的其他人。
"""
from collections import deque
from dataclasses import dataclass
import logging
import math
from threading import Lock
import time
from typing import Callable
import uuid

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException

from app.config import get_settings
from app.db import get_pool, get_redis
from app.deps import get_owner_id
from app.services import audit

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class SlidingWindowLimiter:
    """固定窗口内最多放行 limit 次；窗口滑动，过期记录当场清掉。"""

    _MAX_TRACKED_KEYS = 2048

    def __init__(self, limit: int, window_seconds: float = 60.0,
                 clock: Callable[[], float] = time.monotonic):
        if limit <= 0:
            raise ValueError("limit 必须大于 0")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> RateLimitDecision:
        """记一次请求；超限时给出建议的 Retry-After 秒数。"""
        now = self._clock()
        with self._lock:
            self._prune(now)
            hits = self._hits.setdefault(key, deque())
            cutoff = now - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = max(1, math.ceil(hits[0] + self.window_seconds - now))
                return RateLimitDecision(False, retry_after)
            hits.append(now)
            return RateLimitDecision(True)

    def _prune(self, now: float) -> None:
        """键太多时清掉已过期或空的记录，避免每个新身份都永久占一个键。"""
        if len(self._hits) <= self._MAX_TRACKED_KEYS:
            return
        cutoff = now - self.window_seconds
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]

    def reset(self) -> None:
        """清空计数；测试与本地切换身份时用。"""
        with self._lock:
            self._hits.clear()


_limiter = SlidingWindowLimiter(get_settings().rate_limit_per_minute)

# Redis 原子滑动窗口：多副本共享同一份计数，避免每个进程各放行一份。
_REDIS_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = 0
  if oldest[2] then retry = math.ceil(tonumber(oldest[2]) + window - now) end
  return {0, retry}
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(window))
return {1, 0}
"""


class RedisSlidingWindowLimiter:
    """Redis 版滑动窗口；键按身份隔离，值用时间戳排序集合。"""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        if limit <= 0:
            raise ValueError("limit 必须大于 0")
        self.limit = limit
        self.window_seconds = window_seconds

    async def check(self, redis: aioredis.Redis, key: str) -> RateLimitDecision:
        now = time.time()
        allowed, retry = await redis.eval(
            _REDIS_LUA,
            1,
            f"ragent:ratelimit:{key}",
            now,
            self.window_seconds,
            self.limit,
            f"{now}:{uuid.uuid4().hex}",
        )
        return RateLimitDecision(bool(allowed), int(retry))


_redis_limiter = RedisSlidingWindowLimiter(get_settings().rate_limit_per_minute)


async def limit_requests(
    owner_id: str = Depends(get_owner_id),
    redis: aioredis.Redis = Depends(get_redis),
    pool=Depends(get_pool),
) -> None:
    """POST /requests 的限流依赖；超限直接 429，并带 Retry-After。"""
    if redis is None:
        decision = _limiter.check(owner_id)
    else:
        try:
            decision = await _redis_limiter.check(redis, owner_id)
        except aioredis.RedisError:
            # Redis 抖动时退回进程内限流：可用性优先，至少不会完全放开。
            log.warning("Redis rate limit unavailable; falling back to process-local")
            decision = _limiter.check(owner_id)
    if not decision.allowed:
        await audit.record(pool, owner_id, "rate_limited", retry_after=decision.retry_after)
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后再试。",
            headers={"Retry-After": str(decision.retry_after)},
        )
