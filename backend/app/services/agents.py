"""Agent 用例流程：项目内新建/列出 Agent。模型共用全局配置，此处不涉及。"""
import asyncpg

from app.repositories import agents


async def create_agent(
    pool: asyncpg.Pool,
    project_id,
    name: str,
    persona: str,
    system_prompt: str,
    use_rag: bool,
) -> dict:
    """在项目下新建一个 Agent。"""
    async with pool.acquire() as conn:
        row = await agents.insert_agent(
            conn, project_id, name, persona, system_prompt, use_rag
        )
    return dict(row)


async def list_agents(pool: asyncpg.Pool, project_id) -> list[dict]:
    """列出项目下全部 Agent，供项目内切换。"""
    async with pool.acquire() as conn:
        rows = await agents.list_agents_by_project(conn, project_id)
    return [dict(r) for r in rows]
