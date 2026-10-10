"""llm_config 表读写：只做 SQL，不含业务判断。

v1.2（P1）：从「全库单行」改成「每个 owner 一行」。
写入侧一律以 owner_id 为冲突键，不再出现固定主键 1 —— 主键交给序列，
业务上唯一的那把钥匙是 owner_id（由 idx_llm_config_owner 唯一索引保证）。
"""
import asyncpg


async def get_config(conn: asyncpg.Connection, owner_id: str) -> asyncpg.Record | None:
    """读某个身份的配置行；没有则返回 None（由 service 决定用 env 给他播种）。

    按 owner 查而不是 WHERE id = 1：每个人的 API Key 必须互相隔离，
    共用一把 key 等于让任何访客花掉配置者的额度。
    """
    return await conn.fetchrow(
        "SELECT base_url, api_key, model FROM llm_config WHERE owner_id = $1",
        owner_id,
    )


async def upsert_config(
    conn: asyncpg.Connection, owner_id: str, base_url: str, api_key: str, model: str
) -> None:
    """写入/更新某身份的配置行：冲突键是 owner_id，冲突则覆盖并刷新时间。

    不写 id：它由 llm_config_id_seq 的 DEFAULT nextval 取号（P0 迁移里建的序列）。
    如果这里还沿用旧写法硬塞 VALUES (1, ...)，第二个身份播种时会直接撞主键。
    """
    await conn.execute(
        """
        INSERT INTO llm_config (owner_id, base_url, api_key, model, updated_at)
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (owner_id) DO UPDATE
        SET base_url = EXCLUDED.base_url,
            api_key = EXCLUDED.api_key,
            model = EXCLUDED.model,
            updated_at = now()
        """,
        owner_id,
        base_url,
        api_key,
        model,
    )
