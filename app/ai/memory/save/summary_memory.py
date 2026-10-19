import os
from datetime import datetime

from dotenv import load_dotenv
from psycopg_pool import AsyncConnectionPool

load_dotenv()

# 全局异步连接池（main.py lifespan中调用open()/close()）
pool: AsyncConnectionPool | None = None


async def open_pool():
    """创建并打开连接池 + 幂等建表（兼容其他项目建的旧表结构，缺列自动补）"""
    global pool
    pool = AsyncConnectionPool(
        conninfo=os.getenv("POSTGRESQL_URL"),
        min_size=2,
        max_size=5,
        open=False,
    )
    await pool.open()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS conversation_summary (
                    session_id TEXT PRIMARY KEY,
                    summary    TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # 兼容旧学习项目建的表（无updated_at列）
            await cur.execute("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name='conversation_summary' AND column_name='updated_at'
            """)
            if (await cur.fetchone())[0] == 0:
                await cur.execute("ALTER TABLE conversation_summary ADD COLUMN updated_at TIMESTAMP DEFAULT NOW()")
        await conn.commit()


async def close_pool():
    global pool
    if pool is not None:
        await pool.close()
        pool = None


class SummaryMemory:
    """短期记忆-摘要记忆：PostgreSQL，一个会话一条摘要，LLM增量更新后upsert"""

    def __init__(self, session_id: str):
        self.session_id = session_id

    # 查询摘要
    async def query(self) -> str:
        if pool is None:
            return ""
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT summary FROM conversation_summary WHERE session_id=%s",
                    (self.session_id,),
                )
                row = await cur.fetchone()
        return row[0] if row else ""

    # 保存/更新摘要（upsert）
    async def save(self, summary: str):
        if pool is None:
            return
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO conversation_summary(session_id, summary, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (session_id)
                    DO UPDATE SET summary = EXCLUDED.summary, updated_at = NOW()
                    """,
                    (self.session_id, summary),
                )
        # commit由psycopg_pool自动管理（连接上下文退出时提交）
