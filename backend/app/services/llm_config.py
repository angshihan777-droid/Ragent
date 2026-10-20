"""LLM 配置用例流程：读取生效配置、保存配置、代理拉取模型列表。

放在 service 层是因为它编排了「库里没有就用环境变量播种」「空密钥则保留原值」
这类业务规则，而不是单条 SQL；worker 也复用这里的读取逻辑拿到生效配置。

v1.2（P1）：全部按 owner 维度。环境变量只作「每个身份的首次种子」，
播种出来的行归这个身份所有，之后各自改各自的，互不影响。
"""
import asyncpg
from openai import AsyncOpenAI

from app.config import get_settings
from app.repositories import llm_config as repo

# DeepSeek 官方价（元 / 1K tokens），取「高峰时段 + 缓存未命中」作为保守参考价。
# 来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing（2026-10）
# 只用于配置页预填，用户保存后以库里的值为准。
_DEEPSEEK_PRICES: dict[str, tuple[float, float]] = {
    "deepseek-flash": (0.002, 0.008),
    "deepseek-v4-flash": (0.002, 0.008),
    "deepseek-v4-flash-vision-exp": (0.002, 0.008),
    # 旧模型名仍可能出现在存量配置里，按 Flash 价给参考值。
    "deepseek-chat": (0.002, 0.008),
    "deepseek-v4-pro": (0.009, 0.027),
    "deepseek-reasoner": (0.009, 0.027),
}


def suggest_cost_prices(base_url: str, model: str) -> tuple[float | None, float | None]:
    """按服务地址与模型名给出参考单价；未知组合返回 (None, None)。

    只认 DeepSeek 官方地址，避免把 DeepSeek 的价格套到别家 OpenAI 兼容服务上。
    模型名允许带日期/版本后缀（如 deepseek-v4-pro-0813），取最长前缀匹配。
    """
    if "deepseek.com" not in (base_url or "").lower():
        return None, None
    name = (model or "").strip().lower()
    for candidate in sorted(_DEEPSEEK_PRICES, key=len, reverse=True):
        if name == candidate or name.startswith(candidate + "-"):
            return _DEEPSEEK_PRICES[candidate]
    return None, None


async def get_effective_config(pool: asyncpg.Pool, owner_id: str) -> dict:
    """返回某身份真正生效的配置：他自己有就用他的，没有就用环境变量给他播种一行。

    为什么以库为准：api 和 worker 两个进程不共享内存，只有数据库是共享真相；
    环境变量只作首次种子，改配置后一律以库为准，worker 才能读到最新值。

    为什么不做「全局默认 + 个人覆盖」：密钥是要花钱的资源，
    做成可继承的默认值等于新访客一进来就能用配置者的额度。宁可让每个人自己填一次。
    """
    async with pool.acquire() as conn:
        row = await repo.get_config(conn, owner_id)
        if row is None:
            # 这个身份第一次用，用 .env 里的值给他播一行种子，之后都以库为准
            s = get_settings()
            await repo.upsert_config(
                conn, owner_id, s.llm_base_url, s.llm_api_key, s.llm_model,
                s.llm_reasoning_effort, s.cost_input_per_1k, s.cost_output_per_1k,
            )
            return {
                "base_url": s.llm_base_url,
                "api_key": s.llm_api_key,
                "model": s.llm_model,
                "reasoning_effort": s.llm_reasoning_effort,
                "cost_input_per_1k": s.cost_input_per_1k,
                "cost_output_per_1k": s.cost_output_per_1k,
            }
    return {
        "base_url": row["base_url"],
        "api_key": row["api_key"],
        "model": row["model"],
        # 库里没存过（NULL）时回落到环境变量默认，而不是当成「不许推理」。
        "reasoning_effort": row["reasoning_effort"] or get_settings().llm_reasoning_effort,
        # 单价是模型配置的一部分：按身份存储，前端改完立即对统计生效。
        "cost_input_per_1k": float(row["cost_input_per_1k"] or 0),
        "cost_output_per_1k": float(row["cost_output_per_1k"] or 0),
    }


async def get_config_view(pool: asyncpg.Pool, owner_id: str) -> dict:
    """给前端看的配置：只回 base_url 和 model，密钥只回「是否已设置」不回显明文。"""
    cfg = await get_effective_config(pool, owner_id)
    suggested_input, suggested_output = suggest_cost_prices(cfg["base_url"], cfg["model"])
    return {
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "key_set": bool(cfg["api_key"]),
        "reasoning_effort": cfg["reasoning_effort"],
        "cost_input_per_1k": cfg["cost_input_per_1k"],
        "cost_output_per_1k": cfg["cost_output_per_1k"],
        "cost_input_suggested": suggested_input,
        "cost_output_suggested": suggested_output,
    }


async def get_cost_prices(pool: asyncpg.Pool, owner_id: str) -> tuple[float, float]:
    """只读成本单价，供统计接口使用。

    和 get_effective_config 的区别：没有配置行时直接回落到环境变量种子，
    不写库。GET /metrics/summary 是只读接口，不应该顺手创建配置行。
    """
    async with pool.acquire() as conn:
        row = await repo.get_config(conn, owner_id)
    if row is None:
        s = get_settings()
        return s.cost_input_per_1k, s.cost_output_per_1k
    return float(row["cost_input_per_1k"] or 0), float(row["cost_output_per_1k"] or 0)


async def save_config(
    pool: asyncpg.Pool,
    owner_id: str,
    base_url: str,
    model: str,
    api_key: str | None,
    reasoning_effort: str | None = None,
    cost_input_per_1k: float | None = None,
    cost_output_per_1k: float | None = None,
) -> None:
    """保存配置：字段为 None/空表示「不改这一项」，保留库里原值。

    为什么密钥和推理强度都用「空=不改」而不是「空=清空」：前端不回显密钥，
    也不一定每次都带上所有字段，按「空即清空」处理会把用户没碰过的配置抹掉。
    """
    async with pool.acquire() as conn:
        current = await get_effective_config(pool, owner_id)
        if not api_key:
            api_key = current["api_key"]
        if not reasoning_effort:
            reasoning_effort = current["reasoning_effort"]
        # 单价用 None 表示「这次不传、保留原值」；0 是用户明确选择「不估算」。
        if cost_input_per_1k is None:
            cost_input_per_1k = current["cost_input_per_1k"]
        if cost_output_per_1k is None:
            cost_output_per_1k = current["cost_output_per_1k"]
        await repo.upsert_config(
            conn, owner_id, base_url, api_key, model, reasoning_effort,
            cost_input_per_1k, cost_output_per_1k,
        )


async def list_models(base_url: str, api_key: str) -> list[str]:
    """代理请求 {base_url}/models 拉取可用模型列表，返回模型 id 数组。

    为什么后端代理而不前端直连：密钥不该出现在浏览器里，且能规避跨域；
    OpenAI 兼容服务统一是 GET /models，自定义地址/DeepSeek 都走同一路径。
    """
    # 用 openai SDK 自带的 models.list()，不手拼 URL 和鉴权头；和 ChatOpenAI 是同一个客户端。
    # max_retries=0：保持原来“失败立刻告诉前端”的行为，不让用户等 SDK 默认的重试。
    async with AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=15, max_retries=0) as client:
        page = await client.models.list()
    return [m.id for m in page.data]
