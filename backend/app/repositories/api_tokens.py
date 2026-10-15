"""api_tokens 表的数据访问：只写 SQL，不做策略。

「什么算合法令牌」「非法时回什么状态码」由 app.deps 决定，
这里和 repositories 下其他文件一样，只负责把语句写对。
"""
import asyncpg

# 命中即返回身份。撤销用 revoked_at IS NULL 表达，不做物理删除，
# 否则审计就答不出「这枚令牌存在过、什么时候被停的」。
_QUERY_OWNER = """
SELECT owner_id FROM api_tokens
WHERE token_hash = $1 AND revoked_at IS NULL
"""

# last_used_at 是运维信息，不是业务事实：每个请求都写会让读接口凭空多一次写库。
# 只在「从没记过」或「上次记录已超过一小时」时更新，正常情况下这条 UPDATE 匹配 0 行。
_QUERY_TOUCH = """
UPDATE api_tokens SET last_used_at = now()
WHERE token_hash = $1
  AND (last_used_at IS NULL OR last_used_at < now() - interval '1 hour')
"""

_QUERY_INSERT = """
INSERT INTO api_tokens (token_hash, owner_id, name)
VALUES ($1, $2, $3)
RETURNING id, owner_id, name, created_at
"""

_COLUMNS = "id, owner_id, name, created_at, last_used_at, revoked_at"


async def resolve_owner(conn: asyncpg.Connection, token_hash: str) -> str | None:
    """按令牌哈希查身份。查不到与已撤销都返回 None，对外不区分这两者。"""
    return await conn.fetchval(_QUERY_OWNER, token_hash)


async def touch_last_used(conn: asyncpg.Connection, token_hash: str) -> None:
    """尽力记录最近使用时间。失败不影响鉴权结果，调用方不必回滚。"""
    await conn.execute(_QUERY_TOUCH, token_hash)


async def insert_token(
    conn: asyncpg.Connection, token_hash: str, owner_id: str, name: str
) -> asyncpg.Record:
    """写入一枚令牌。明文不在这里出现 —— 调用方只把哈希交进来。"""
    return await conn.fetchrow(_QUERY_INSERT, token_hash, owner_id, name)


async def list_tokens(conn: asyncpg.Connection, owner_id: str | None) -> list[asyncpg.Record]:
    """列出令牌（永远不含明文）。owner_id 为 None 表示不筛身份。"""
    if owner_id is None:
        return await conn.fetch(
            f"SELECT {_COLUMNS} FROM api_tokens ORDER BY created_at DESC"
        )
    return await conn.fetch(
        f"SELECT {_COLUMNS} FROM api_tokens WHERE owner_id = $1 ORDER BY created_at DESC",
        owner_id,
    )


async def revoke_token_by_id(conn: asyncpg.Connection, token_id) -> bool:
    """撤销一枚令牌；返回是否真的撤销了一行（重复撤销返回 False）。"""
    result = await conn.execute(
        "UPDATE api_tokens SET revoked_at = now() WHERE id = $1 AND revoked_at IS NULL",
        token_id,
    )
    return result.endswith(" 1")
