"""请求级公共依赖：取当前身份、校验资源归属。

为什么集中成依赖而不是每个路由函数里手写一遍：P1 要覆盖 6 个 router 共约 16 个端点，
手写必然漏——漏掉的那个端点就是一个越权读接口，而且从代码上看不出异常（它「能用」）。
声明成 Depends 之后，端点签名里有没有归属校验是肉眼可见的。

统一返回 404 而不是 403：403 等于告诉对方「这个 id 真实存在，只是不归你」，
配合可枚举的 id 就是一个存在性探测接口。不存在与无权限对外是同一个回答。
"""
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Request

from app.db import get_pool
from app.repositories import projects as project_repo


def get_owner_id(request: Request) -> str:
    """取当前请求的身份 id。

    值由 OwnerCookieMiddleware 放进 request.state，这里不兜底生成：
    读不到说明中间件没装或被摘掉，那是部署事故，必须当场炸出来，
    静默兜一个新身份只会让所有人看到空数据，反而更难查。
    """
    owner_id = getattr(request.state, "owner_id", None)
    if not owner_id:
        raise RuntimeError("身份中间件未生效：request.state.owner_id 缺失")
    return owner_id


def _as_uuid(raw) -> UUID | None:
    """把路径参数收成 UUID；不是合法 uuid 返回 None。

    为什么要先收一遍：部分端点的路径参数声明成 str（历史签名），直接喂给 asyncpg
    的 uuid 参数会抛 DataError → 500。对调用方来说「乱填一个 id」本该是 404 而不是服务器错误。
    """
    if isinstance(raw, UUID):
        return raw
    try:
        return UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None


async def _require_owner_match(pool: asyncpg.Pool, resolver, resource_id, owner_id: str) -> None:
    """通用归属断言：解析出资源归属的身份，与当前身份不一致即 404。"""
    target = _as_uuid(resource_id)
    if target is None:
        raise HTTPException(status_code=404, detail="not found")
    async with pool.acquire() as conn:
        actual = await resolver(conn, target)
    # actual is None 表示资源不存在；actual != owner_id 表示存在但不归你。对外同一个回答。
    if actual != owner_id:
        raise HTTPException(status_code=404, detail="not found")


async def require_owned_project(
    project_id: UUID,
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> UUID:
    """校验路径上的 project_id 属于当前身份，返回它供端点继续使用。"""
    async with pool.acquire() as conn:
        row = await project_repo.get_project(conn, project_id, owner_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project_id


async def require_owned_thread(
    thread_id: str,
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> str:
    """校验路径上的 thread_id 经 project 归当前身份所有。"""
    await _require_owner_match(pool, project_repo.owner_of_thread, thread_id, owner_id)
    return thread_id


async def require_owned_document(
    document_id: UUID,
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> UUID:
    """校验路径上的 document_id 经 project 归当前身份所有。"""
    await _require_owner_match(pool, project_repo.owner_of_document, document_id, owner_id)
    return document_id


async def require_owned_request(
    request_id: UUID,
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> UUID:
    """校验路径上的 request_id 经 thread → project 归当前身份所有。

    SSE 端点（GET /requests/{id}/stream）必须挂这个依赖：它不读库表、只订阅 Redis 频道，
    看上去「没碰数据」，但流里推的是完整回答正文——知道 request_id 就能偷听别人的对话。
    这是整个 P1 最容易漏的一个点，因为漏了功能完全正常。
    """
    await _require_owner_match(pool, project_repo.owner_of_request, request_id, owner_id)
    return request_id

async def assert_owned_thread(pool: asyncpg.Pool, thread_id: str, owner_id: str) -> None:
    """校验「请求体里带的」thread_id 归当前身份所有，不属于则 404。

    为什么单独留一个非依赖版本：POST /requests 的会话 id 在 body 里而不是路径上，
    FastAPI 依赖拿不到它（依赖若自己再声明一次 body，同一请求会被解析两遍）。
    校验逻辑仍复用 _require_owner_match，判定口径与路径参数那几个依赖完全一致。
    """
    await _require_owner_match(pool, project_repo.owner_of_thread, thread_id, owner_id)

async def assert_owned_project(pool: asyncpg.Pool, project_id, owner_id: str) -> None:
    """校验「不在路径上」的 project_id 归当前身份所有，不属于则 404。

    documents 那几个端点的 project_id 分别来自 JSON body、multipart Form 和 query，
    三种位置都不能靠 require_owned_project（它声明的是路径参数）。与其给每种位置写一个依赖，
    不如在端点里显式 await 一次：调用点看得见，漏了也容易在 review 里发现。
    """
    target = _as_uuid(project_id)
    if target is None:
        raise HTTPException(status_code=404, detail="project not found")
    async with pool.acquire() as conn:
        # get_project 本身就是「id + owner」双条件查询，查不到即「不存在或不归你」
        row = await project_repo.get_project(conn, target, owner_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")