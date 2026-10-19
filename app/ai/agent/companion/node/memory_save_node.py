import asyncio

from app.ai.agent.companion.state.companion_state import CompanionState
from app.common.mysql_db import mysql_db

"""
记忆保存节点：本轮对话（用户问题+AI回复+情绪）入库MySQL，
然后后台异步更新四层记忆（摘要/长期/画像/工作），不阻塞SSE结束
MemoryManager在这里被调用
"""


async def memory_save_node(state: CompanionState):
    try:
        with mysql_db() as db:
            # 用户消息留档
            db["cursor"].execute(
                "INSERT INTO messages(session_id, role, content) VALUES(%s,%s,%s)",
                (state["session_id"], "user", state["question"]),
            )
            # AI回复留档（附带本轮识别到的用户情绪）
            db["cursor"].execute(
                "INSERT INTO messages(session_id, role, content, emotion) VALUES(%s,%s,%s,%s)",
                (state["session_id"], "assistant", state["ai_answer"], state["emotion"]),
            )
            # 会话自动命名：第一轮对话后用用户的问题作为会话标题
            db["cursor"].execute(
                "SELECT title FROM conversations WHERE session_id=%s", (state["session_id"],)
            )
            row = db["cursor"].fetchone()
            if row and row["title"] == "新的对话":
                title = state["question"][:15] + ("..." if len(state["question"]) > 15 else "")
                db["cursor"].execute(
                    "UPDATE conversations SET title=%s WHERE session_id=%s",
                    (title, state["session_id"]),
                )
    except Exception as e:
        print(f"消息落库失败:{e}")

    # 后台异步更新四层记忆（对话已流式返回给用户，记忆更新不阻塞）
    async def _update_memories():
        from app.ai.memory.manager.memory_manager import MemoryManager

        try:
            manager = MemoryManager(state["session_id"], state["user_id"])
            await manager.update(state["question"], state["ai_answer"], state["emotion"])
        except Exception as e:
            print(f"记忆后台更新异常:{e}")

    asyncio.create_task(_update_memories())
    return {}
