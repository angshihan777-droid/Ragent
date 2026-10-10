"""projects 表读写：只做单条 SQL，不含业务判断。"""
import asyncpg


async def insert_project(
    conn: asyncpg.Connection, owner_id: str, name: str, description: str
) -> asyncpg.Record:
    """新建项目，返回完整行。owner_id 必传：它是整个归属链唯一的锚点。"""
    return await conn.fetchrow(
        """
        INSERT INTO projects (owner_id, name, description)
        VALUES ($1, $2, $3)
        RETURNING id, name, description, created_at
        """,
        owner_id,
        name,
        description,
    )


async def list_projects(conn: asyncpg.Connection, owner_id: str) -> list[asyncpg.Record]:
    """按创建时间正序列出该身份名下的项目，供左侧项目栏展示。

    过滤放在 SQL 里而不是取回来再筛：前端筛等于把别人的数据先发到浏览器，
    抓包就能看到全部，那不叫隔离。
    """
    return await conn.fetch(
        """
        SELECT id, name, description, created_at
        FROM projects
        WHERE owner_id = $1
        ORDER BY created_at
        """,
        owner_id,
    )


async def get_project(
    conn: asyncpg.Connection, project_id, owner_id: str
) -> asyncpg.Record | None:
    """按 id 取该身份名下的单个项目。

    owner_id 直接进 WHERE，而不是取回来再比对：把「不存在」和「不属于你」合并成同一个
    返回值 None，上层统一收成 404，调用方没有机会不小心把两者区分开来告诉攻击者。
    """
    return await conn.fetchrow(
        """
        SELECT id, name, description, created_at
        FROM projects
        WHERE id = $1 AND owner_id = $2
        """,
        project_id,
        owner_id,
    )


# ---- 归属解析：把「这个 id 归谁」集中在这里，deps 只比对结果，不自己拼 join ----
#
# 为什么统一走「解析出 owner_id 再比对」而不是每个表各写一个 exists 判断：
# 归属只挂在 projects 上，其余表沿外键链传导，join 路径写错一次就是一个越权口子。
# 集中成三个函数后，路径只有这一处，审的时候一眼看完。
#
# 注意 threads.id 是 UUID，而 messages.thread_id / agent_run_requests.thread_id 是 TEXT
# （历史设计，见 schema.sql 开头），PG 对 text = uuid 不做隐式比较，必须显式转型。
# 方向选 t.id::text = r.thread_id 而不是 r.thread_id::uuid：TEXT 列里只要存在一行不是
# 合法 uuid 的历史脏数据，uuid 侧的转型就会让整条查询报错——而报错点在归属校验上，
# 等于任何人都过不去。往 text 转永远不会失败，最坏情况只是匹配不上，退化成 404。


async def owner_of_thread(conn: asyncpg.Connection, thread_id) -> str | None:
    """会话 → 项目 → 身份；会话不存在返回 None。"""
    return await conn.fetchval(
        """
        SELECT p.owner_id
        FROM threads t
        JOIN projects p ON p.id = t.project_id
        WHERE t.id = $1
        """,
        thread_id,
    )


async def owner_of_document(conn: asyncpg.Connection, document_id) -> str | None:
    """资料 → 项目 → 身份；资料不存在返回 None。"""
    return await conn.fetchval(
        """
        SELECT p.owner_id
        FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE d.id = $1
        """,
        document_id,
    )


async def owner_of_request(conn: asyncpg.Connection, request_id) -> str | None:
    """请求 → 会话 → 项目 → 身份；请求不存在返回 None。

    刻意不用 agent_run_requests.user_id 判断：那一列在 P1 之前写的是固定值 'u1'，
    存量行全都对不上真实身份。项目上的 owner_id 才是唯一权威锚点。
    """
    return await conn.fetchval(
        """
        SELECT p.owner_id
        FROM agent_run_requests r
        JOIN threads t ON t.id::text = r.thread_id
        JOIN projects p ON p.id = t.project_id
        WHERE r.id = $1
        """,
        request_id,
    )


async def delete_project(conn: asyncpg.Connection, project_id) -> None:
    """硬删项目：threads/documents/chunks 靠外键 ON DELETE CASCADE 一并清除。

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
