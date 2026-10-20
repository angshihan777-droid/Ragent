"""滑动窗口限流：用可控时钟验证窗口边界，不依赖真实时间。"""
from app.guards.rate_limit import SlidingWindowLimiter


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_blocks_after_limit_and_reports_retry_after():
    clock = _Clock()
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60, clock=clock)

    assert all(limiter.check("u-1").allowed for _ in range(3))
    denied = limiter.check("u-1")
    assert denied.allowed is False
    assert denied.retry_after == 60


def test_window_slides_so_old_hits_expire():
    clock = _Clock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)

    assert limiter.check("u-1").allowed
    assert not limiter.check("u-1").allowed
    clock.now += 61
    assert limiter.check("u-1").allowed


def test_keys_are_isolated():
    clock = _Clock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)

    assert limiter.check("u-1").allowed
    assert limiter.check("u-2").allowed
    assert not limiter.check("u-1").allowed


def test_reset_clears_all_keys():
    clock = _Clock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)

    assert limiter.check("u-1").allowed
    limiter.reset()
    assert limiter.check("u-1").allowed


def test_prunes_stale_keys_to_bound_memory():
    clock = _Clock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)

    for i in range(3000):
        limiter.check(f"u-{i}")
    assert len(limiter._hits) > limiter._MAX_TRACKED_KEYS

    clock.now += 61
    limiter.check("fresh")
    assert len(limiter._hits) < 10
