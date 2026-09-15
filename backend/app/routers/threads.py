"""会话消息路由：回放某会话的历史消息，供切换会话时加载对话。"""
import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_pool
from app.schemas import MessageOut
from app.services import threads as thread_service

router = APIRouter(prefix="/threads", tags=["threads"])


@router.get("/{thread_id}/messages", response_model=list[MessageOut])
async def list_thread_messages(
    thread_id: str, pool: asyncpg.Pool = Depends(get_pool)
):
    """按时间正序回放一个会话的全部消息。"""
    return await thread_service.list_thread_messages(pool, thread_id)


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(thread_id: str, pool: asyncpg.Pool = Depends(get_pool)):
    """删一个会话及其全部对话数据；不存在返回 404。"""
    ok = await thread_service.delete_thread(pool, thread_id)
    if not ok:
        raise HTTPException(status_code=404, detail="thread not found")
