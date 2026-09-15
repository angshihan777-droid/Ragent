"""llm_config 单行表读写：只做 SQL，不含业务判断。"""
import asyncpg


async def get_config(conn: asyncpg.Connection) -> asyncpg.Record | None:
    """读当前配置行；没有则返回 None（由 service 决定用 env 播种）。"""
    return await conn.fetchrow(
        "SELECT base_url, api_key, model FROM llm_config WHERE id = 1"
    )


async def upsert_config(
    conn: asyncpg.Connection, base_url: str, api_key: str, model: str
) -> None:
    """写入/更新唯一配置行：主键固定为 1，冲突则覆盖并刷新时间。"""
    await conn.execute(
        """
        INSERT INTO llm_config (id, base_url, api_key, model, updated_at)
        VALUES (1, $1, $2, $3, now())
        ON CONFLICT (id) DO UPDATE
        SET base_url = EXCLUDED.base_url,
            api_key = EXCLUDED.api_key,
            model = EXCLUDED.model,
            updated_at = now()
        """,
        base_url,
        api_key,
        model,
    )
