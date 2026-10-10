"""LLM 配置路由：保持薄，只收发参数，读写/播种/拉模型逻辑在 llm_config service。

这里的每个端点都要显式取 owner_id：配置里存着真金白银的 api_key，
按身份隔离之后，A 的密钥绝不能被 B 读到或用来拉模型（哪怕只是拉列表也在花对方的额度）。
"""
import asyncpg
import openai
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.db import get_pool
from app.deps import get_owner_id
from app.middleware.owner import (
    OWNER_COOKIE_OVERRIDDEN,
    is_secure_scheme,
    normalize_owner_id,
    set_owner_cookie,
)
from app.schemas import (
    IdentityOut,
    ListModelsIn,
    ListModelsOut,
    LLMConfigView,
    SaveLLMConfigIn,
    SwitchIdentityIn,
)
from app.services import llm_config as svc

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/llm", response_model=LLMConfigView)
async def get_llm_config(
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """读当前生效配置；密钥只回「是否已设置」，不回显明文。"""
    view = await svc.get_config_view(pool, owner_id)
    return LLMConfigView(**view)


@router.put("/llm", response_model=LLMConfigView)
async def save_llm_config(
    body: SaveLLMConfigIn,
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """保存配置；空密钥保留原值，保存后回读一遍作为确认。"""
    await svc.save_config(pool, owner_id, body.base_url, body.model, body.api_key)
    view = await svc.get_config_view(pool, owner_id)
    return LLMConfigView(**view)


@router.post("/llm/models", response_model=ListModelsOut)
async def list_llm_models(
    body: ListModelsIn,
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """代理拉取可选模型列表：入参没给密钥时，用「自己那份」已存的密钥去拉。"""
    api_key = body.api_key
    if not api_key:
        # 只回落到当前身份自己的配置，不共享别人的密钥
        cfg = await svc.get_effective_config(pool, owner_id)
        api_key = cfg["api_key"]
    try:
        models = await svc.list_models(body.base_url, api_key)
    except openai.OpenAIError as e:
        # 上游地址/密钥不对时给前端明确 400，而不是 500 内部错
        raise HTTPException(status_code=400, detail=f"拉取模型失败: {e}")
    return ListModelsOut(models=models)


# ---- 身份显示与切换（§3.7）----

@router.get("/identity", response_model=IdentityOut)
async def get_identity(owner_id: str = Depends(get_owner_id)):
    """回当前浏览器的身份 id，供前端展示与复制。

    Cookie 是 httpOnly 的，前端读不到，所以必须由后端回一个接口告诉它「你是谁」，
    否则用户没有任何办法把自己的身份迁到另一台机器上。
    """
    return IdentityOut(owner_id=owner_id)


@router.post("/identity", response_model=IdentityOut)
async def switch_identity(
    body: SwitchIdentityIn,
    request: Request,
    response: Response,
):
    """覆写身份 Cookie：在新浏览器恢复原有数据，也用于认领 legacy-u1 的存量项目。

    这个接口不做任何鉴权——它本来就是「知道 id 即可访问」的设计，
    id 等同于密码，前端界面上必须把这句话写给用户看。
    """
    target = normalize_owner_id(body.owner_id)
    if target is None:
        # 非法 id 直接 400：如果放进 Cookie，之后每个请求都会带着一个永远查不到数据的身份，
        # 表现是「登录成功但什么都看不见」，比当场报错难查得多
        raise HTTPException(status_code=400, detail="身份 id 只允许字母、数字、下划线和连字符，长度 1~64")
    secure = is_secure_scheme(request.url.scheme, request.headers.get("x-forwarded-proto"))
    set_owner_cookie(response, target, secure=secure)
    # 告诉中间件「本请求已自行下发 Cookie」，否则它会再追加一个旧身份的 Set-Cookie，
    # 两个同名 Cookie 谁生效取决于浏览器，切换会变成时好时坏的随机行为
    # setattr 而不是写 state.__dict__：Starlette 的 State.__setattr__ 才会落到 scope["state"]，
    # 而中间件读的正是那个 dict，写错位置的话这个开关静默失效
    setattr(request.state, OWNER_COOKIE_OVERRIDDEN, True)
    return IdentityOut(owner_id=target)