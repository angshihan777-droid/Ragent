"""显式索引维护入口：python -m app.reindex。运行前备份数据库并暂停资料写入。"""
import asyncio
import asyncpg
from app.config import get_settings
from app.services.rag import reindex_documents


async def main():
    pool = await asyncpg.create_pool(get_settings().database_url)
    try:
        count = await reindex_documents(pool)
        print(f"Reindexed {count} documents")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
