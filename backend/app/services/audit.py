"""安全审计：结构化记录，不阻塞主请求。

审计写失败只记服务端日志，不让「记录失败」变成「请求失败」；
详情只放规则编号、长度、重试秒数这类摘要，不落用户原文。
"""
import json
import logging

log = logging.getLogger(__name__)


async def record(pool, owner_id: str, action: str, **detail) -> None:
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO audit_logs(owner_id, action, detail) VALUES($1, $2, $3::jsonb)",
                owner_id,
                action,
                json.dumps(detail, ensure_ascii=False),
            )
    except Exception as exc:
        log.warning("Audit write failed action=%s error=%s", action, type(exc).__name__)
