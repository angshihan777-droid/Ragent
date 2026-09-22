"""会话用例流程：项目内新建/列出会话，以及回放某会话的历史消息。"""
import json
import asyncpg

from app.services.errors import public_error
from app.repositories import messages, requests, runs, threads


async def create_thread(
    pool: asyncpg.Pool, project_id, title: str
) -> dict:
    """在项目下新建知识库会话。"""
    async with pool.acquire() as conn:
        row = await threads.insert_thread(conn, project_id, title)
    return dict(row)


async def list_threads(pool: asyncpg.Pool, project_id) -> list[dict]:
    """列出项目下全部会话，最新在前。"""
    async with pool.acquire() as conn:
        rows = await threads.list_threads_by_project(conn, project_id)
    return [dict(r) for r in rows]


async def list_thread_messages(pool: asyncpg.Pool, thread_id: str) -> list[dict]:
    """回放某会话的历史消息（正序），供切换会话时加载对话。"""
    async with pool.acquire() as conn:
        rows = await messages.list_messages_by_thread(conn, thread_id)
    return [
        {"id": r["id"], "role": r["role"], "content": public_error(r["content"]) if r["error"] else r["content"], "error": r["error"], "created_at": r["created_at"], "sources": json.loads(r["sources"]), "steps": json.loads(r["steps"])}
        for r in rows
    ]


async def delete_thread(pool: asyncpg.Pool, thread_id: str) -> bool:
    """删一个会话及其全部对话数据；会话不存在返回 False。

    删除顺序关键：messages/agent_run_requests/agent_runs 用 thread_id 文本关联、无外键，
    必须按 run→request→message 的外键依赖顺序显式删，最后再删会话本身。
    整个过程放一个事务，避免删一半留下孤儿数据。
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            if await threads.get_thread(conn, thread_id) is None:
                return False
            ids = [thread_id]
            await runs.delete_runs_by_threads(conn, ids)
            await requests.delete_requests_by_threads(conn, ids)
            await messages.delete_messages_by_threads(conn, ids)
            await threads.delete_thread(conn, thread_id)
    return True
