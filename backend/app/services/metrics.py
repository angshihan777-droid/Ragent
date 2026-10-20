"""执行用量聚合：只读 agent_runs.usage，不新增表。

usage 由 stream_agent 在每次模型调用结束时汇总，
worker 收尾时随 run 一起落库；这里只负责按身份和时间窗做聚合。
"""
import asyncpg

from app.services import llm_config

_SUMMARY_SQL = """
SELECT
    COALESCE(SUM(COALESCE((r.usage->>'input_tokens')::bigint, 0)), 0)::bigint  AS input_tokens,
    COALESCE(SUM(COALESCE((r.usage->>'output_tokens')::bigint, 0)), 0)::bigint AS output_tokens,
    COALESCE(SUM(COALESCE((r.usage->>'llm_calls')::bigint, 0)), 0)::bigint     AS llm_calls,
    (COUNT(*) FILTER (WHERE r.status = 'done'))::bigint                        AS done_runs,
    (COUNT(*) FILTER (WHERE r.status = 'failed'))::bigint                      AS failed_runs
FROM agent_runs r
JOIN agent_run_requests q ON q.id = r.request_id
WHERE q.user_id = $1
  AND r.created_at >= now() - make_interval(days => $2::int)
"""


def success_rate(done_runs: int, failed_runs: int) -> float | None:
    """成功次数 / 已结束次数；没有已结束的执行时返回 None，不伪造 100%。"""
    finished = done_runs + failed_runs
    if finished <= 0:
        return None
    return round(done_runs / finished, 4)


def estimate_cost(input_tokens: int, output_tokens: int,
                  input_price_per_1k: float, output_price_per_1k: float) -> float | None:
    """按配置单价估算成本；两个单价都没配时返回 None，前端显示「未配置」。"""
    if input_price_per_1k <= 0 and output_price_per_1k <= 0:
        return None
    cost = (input_tokens / 1000) * input_price_per_1k + (output_tokens / 1000) * output_price_per_1k
    return round(cost, 6)


async def get_summary(pool: asyncpg.Pool, owner_id: str, days: int) -> dict:
    """返回当前身份在最近 days 天内的用量与成功率。"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SUMMARY_SQL, owner_id, days)
    # 只读单价：没有配置行时回落到环境变量，不在 GET 请求里创建配置行。
    input_price, output_price = await llm_config.get_cost_prices(pool, owner_id)
    input_tokens = int(row["input_tokens"] or 0)
    output_tokens = int(row["output_tokens"] or 0)
    done_runs = int(row["done_runs"] or 0)
    failed_runs = int(row["failed_runs"] or 0)
    return {
        "days": days,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "llm_calls": int(row["llm_calls"] or 0),
        "done_runs": done_runs,
        "failed_runs": failed_runs,
        "success_rate": success_rate(done_runs, failed_runs),
        "estimated_cost": estimate_cost(
            input_tokens, output_tokens, input_price, output_price,
        ),
    }
