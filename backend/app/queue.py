"""Redis 投递：只搬运「该跑哪个 run」的信号，不持有任何业务状态。

面试点：业务真相全在 PostgreSQL，Redis 只是投递通道；即使 Redis 丢消息，
也能靠 PG 里的 dispatched 请求恢复（后续模块做补偿扫描）。
"""
import redis.asyncio as aioredis

# 待执行 run 的队列键。用最简单的 list：LPUSH 投递、worker 侧 BRPOP 取，天然 FIFO。
QUEUE_KEY = "ragent:runs"


async def enqueue_run(redis: aioredis.Redis, run_id) -> None:
    """把 run_id 投进队列。

    时序关键：调用方必须先提交 PG 事务再调用本函数，
    否则 worker 可能先取到消息却在库里查不到对应的 run。
    """
    await redis.lpush(QUEUE_KEY, str(run_id))
