"""项目用例流程：增删查。删项目要级联清理会话名下的消息/请求/run。"""
import asyncpg

from app.repositories import messages, projects, requests, runs, threads


async def create_project(pool: asyncpg.Pool, name: str, description: str) -> dict:
    """新建项目。"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await projects.insert_project(conn, name.strip(), description)
            await threads.insert_thread(conn, row["id"], "新会话")
    return dict(row)


async def list_projects(pool: asyncpg.Pool) -> list[dict]:
    """列出全部项目，供左侧项目栏展示。"""
    async with pool.acquire() as conn:
        rows = await projects.list_projects(conn)
    return [dict(r) for r in rows]


async def get_project(pool: asyncpg.Pool, project_id) -> dict | None:
    """取单个项目；不存在返回 None。"""
    async with pool.acquire() as conn:
        row = await projects.get_project(conn, project_id)
    return dict(row) if row else None


async def delete_project(pool: asyncpg.Pool, project_id) -> bool:
    """硬删项目及其全部关联数据；项目不存在返回 False。

    删除顺序关键：threads/documents/chunks 有外键 CASCADE 会自动清，
    但 messages/agent_run_requests/agent_runs 用 thread_id 文本关联、无外键，
    必须按 run→request→message 的外键依赖顺序显式删，再删项目触发级联。
    整个过程放一个事务，避免删一半留下孤儿数据。
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            if await projects.get_project(conn, project_id) is None:
                return False
            thread_ids = await projects.thread_ids_of_project(conn, project_id)
            if thread_ids:
                await runs.delete_runs_by_threads(conn, thread_ids)
                await requests.delete_requests_by_threads(conn, thread_ids)
                await messages.delete_messages_by_threads(conn, thread_ids)
            await projects.delete_project(conn, project_id)
    return True
