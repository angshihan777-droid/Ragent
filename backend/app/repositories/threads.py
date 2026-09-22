"""项目会话的数据访问。"""
import asyncpg


async def insert_thread(
    conn: asyncpg.Connection, project_id, title: str
) -> asyncpg.Record:
    """在项目下新建知识库会话，返回完整行。"""
    return await conn.fetchrow(
        """
        INSERT INTO threads (project_id, title)
        VALUES ($1, $2)
        RETURNING id, project_id, title, created_at
        """,
        project_id,
        title,
    )


async def list_threads_by_project(
    conn: asyncpg.Connection, project_id
) -> list[asyncpg.Record]:
    """列出某项目下全部会话，最新的排在前面，供会话列表展示。"""
    return await conn.fetch(
        """
        SELECT id, project_id, title, created_at
        FROM threads
        WHERE project_id = $1
        ORDER BY created_at DESC
        """,
        project_id,
    )


async def get_thread(conn: asyncpg.Connection, thread_id) -> asyncpg.Record | None:
    """按 id 取单个会话；用于校验请求所属会话。"""
    return await conn.fetchrow(
        """
        SELECT id, project_id, title, created_at
        FROM threads
        WHERE id = $1
        """,
        thread_id,
    )


async def delete_thread(conn: asyncpg.Connection, thread_id) -> None:
    """删一个会话本身；它名下的消息/请求/run 由 service 先按外键顺序清理。"""
    await conn.execute("DELETE FROM threads WHERE id = $1", thread_id)
