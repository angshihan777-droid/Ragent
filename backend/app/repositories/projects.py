"""projects 表读写：只做单条 SQL，不含业务判断。"""
import asyncpg


async def insert_project(
    conn: asyncpg.Connection, name: str, description: str
) -> asyncpg.Record:
    """新建项目，返回完整行。"""
    return await conn.fetchrow(
        """
        INSERT INTO projects (name, description)
        VALUES ($1, $2)
        RETURNING id, name, description, created_at
        """,
        name,
        description,
    )


async def list_projects(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """按创建时间正序列出全部项目，供左侧项目栏展示。"""
    return await conn.fetch(
        """
        SELECT id, name, description, created_at
        FROM projects
        ORDER BY created_at
        """
    )


async def get_project(conn: asyncpg.Connection, project_id) -> asyncpg.Record | None:
    """按 id 取单个项目；不存在返回 None，由上层决定 404。"""
    return await conn.fetchrow(
        """
        SELECT id, name, description, created_at
        FROM projects
        WHERE id = $1
        """,
        project_id,
    )


async def delete_project(conn: asyncpg.Connection, project_id) -> None:
    """硬删项目：agents/threads/documents/chunks 靠外键 ON DELETE CASCADE 一并清除。

    messages/agent_run_requests 用 thread_id 文本关联、无外键，
    由 service 层显式清理，避免留下孤儿会话记录。
    """
    await conn.execute("DELETE FROM projects WHERE id = $1", project_id)


async def thread_ids_of_project(
    conn: asyncpg.Connection, project_id
) -> list:
    """取项目下所有会话 id（文本形式），供删项目时清理关联的消息与请求。"""
    rows = await conn.fetch(
        "SELECT id::text AS id FROM threads WHERE project_id = $1",
        project_id,
    )
    return [r["id"] for r in rows]
