"""agents 表读写：只做单条 SQL，不含业务判断。"""
import asyncpg


async def insert_agent(
    conn: asyncpg.Connection,
    project_id,
    name: str,
    persona: str,
    system_prompt: str,
    use_rag: bool,
) -> asyncpg.Record:
    """在项目下新建一个 Agent，返回完整行。"""
    return await conn.fetchrow(
        """
        INSERT INTO agents (project_id, name, persona, system_prompt, use_rag)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, project_id, name, persona, system_prompt, use_rag, created_at
        """,
        project_id,
        name,
        persona,
        system_prompt,
        use_rag,
    )


async def list_agents_by_project(
    conn: asyncpg.Connection, project_id
) -> list[asyncpg.Record]:
    """列出某项目下全部 Agent，供项目内切换。"""
    return await conn.fetch(
        """
        SELECT id, project_id, name, persona, system_prompt, use_rag, created_at
        FROM agents
        WHERE project_id = $1
        ORDER BY created_at
        """,
        project_id,
    )


async def get_agent(conn: asyncpg.Connection, agent_id) -> asyncpg.Record | None:
    """按 id 取单个 Agent。"""
    return await conn.fetchrow(
        """
        SELECT id, project_id, name, persona, system_prompt, use_rag, created_at
        FROM agents
        WHERE id = $1
        """,
        agent_id,
    )
