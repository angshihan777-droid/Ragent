"""LLM 配置用例流程：读取生效配置、保存配置、代理拉取模型列表。

放在 service 层是因为它编排了「库里没有就用环境变量播种」「空密钥则保留原值」
这类业务规则，而不是单条 SQL；worker 也复用这里的读取逻辑拿到生效配置。
"""
import asyncpg
import httpx

from app.config import get_settings
from app.repositories import llm_config as repo


async def get_effective_config(pool: asyncpg.Pool) -> dict:
    """返回当前真正生效的配置：库里有就用库里的，没有就用环境变量播种一行。

    为什么以库为准：api 和 worker 两个进程不共享内存，只有数据库是共享真相；
    环境变量只作首次种子，改配置后一律以库为准，worker 才能读到最新值。
    """
    async with pool.acquire() as conn:
        row = await repo.get_config(conn)
        if row is None:
            # 首次运行库里没有配置，用 .env 里的值播种，之后都以库为准
            s = get_settings()
            await repo.upsert_config(conn, s.llm_base_url, s.llm_api_key, s.llm_model)
            return {"base_url": s.llm_base_url, "api_key": s.llm_api_key, "model": s.llm_model}
    return {"base_url": row["base_url"], "api_key": row["api_key"], "model": row["model"]}


async def get_config_view(pool: asyncpg.Pool) -> dict:
    """给前端看的配置：只回 base_url 和 model，密钥只回「是否已设置」不回显明文。"""
    cfg = await get_effective_config(pool)
    return {
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "key_set": bool(cfg["api_key"]),
    }


async def save_config(
    pool: asyncpg.Pool, base_url: str, model: str, api_key: str | None
) -> None:
    """保存配置：api_key 为空表示「不改密钥」，保留库里原值，避免前端不回显时被清空。"""
    async with pool.acquire() as conn:
        if not api_key:
            current = await get_effective_config(pool)
            api_key = current["api_key"]
        await repo.upsert_config(conn, base_url, api_key, model)


async def list_models(base_url: str, api_key: str) -> list[str]:
    """代理请求 {base_url}/models 拉取可用模型列表，返回模型 id 数组。

    为什么后端代理而不前端直连：密钥不该出现在浏览器里，且能规避跨域；
    OpenAI 兼容服务统一是 GET /models，自定义地址/DeepSeek 都走同一路径。
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            base_url.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
    # OpenAI 兼容返回 {"data": [{"id": "..."}, ...]}，只取 id
    return [m["id"] for m in data.get("data", []) if "id" in m]
