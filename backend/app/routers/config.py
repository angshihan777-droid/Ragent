"""LLM 配置路由：保持薄，只收发参数，读写/播种/拉模型逻辑在 llm_config service。"""
import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_pool
from app.schemas import (
    ListModelsIn,
    ListModelsOut,
    LLMConfigView,
    SaveLLMConfigIn,
)
from app.services import llm_config as svc

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/llm", response_model=LLMConfigView)
async def get_llm_config(pool: asyncpg.Pool = Depends(get_pool)):
    """读当前生效配置；密钥只回「是否已设置」，不回显明文。"""
    view = await svc.get_config_view(pool)
    return LLMConfigView(**view)


@router.put("/llm", response_model=LLMConfigView)
async def save_llm_config(
    body: SaveLLMConfigIn,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """保存配置；空密钥保留原值，保存后回读一遍作为确认。"""
    await svc.save_config(pool, body.base_url, body.model, body.api_key)
    view = await svc.get_config_view(pool)
    return LLMConfigView(**view)


@router.post("/llm/models", response_model=ListModelsOut)
async def list_llm_models(
    body: ListModelsIn,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """代理拉取可选模型列表：入参没给密钥时，用库里已存的密钥去拉。"""
    api_key = body.api_key
    if not api_key:
        cfg = await svc.get_effective_config(pool)
        api_key = cfg["api_key"]
    try:
        models = await svc.list_models(body.base_url, api_key)
    except httpx.HTTPError as e:
        # 上游地址/密钥不对时给前端明确 400，而不是 500 内部错
        raise HTTPException(status_code=400, detail=f"拉取模型失败: {e}")
    return ListModelsOut(models=models)
