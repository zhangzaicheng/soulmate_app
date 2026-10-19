import json

from app.common.mysql_db import mysql_db


class WorkingMemory:
    """工作记忆（giftia设计）：跨会话的对用户的整体了解，始终注入prompt
    MySQL working_memory表：summary(整体了解200字内) / open_topics(待跟进话题) / current_emotion
    """

    def __init__(self, user_id: int):
        self.user_id = user_id

    # 查询工作记忆
    def query(self) -> dict | None:
        with mysql_db() as db:
            db["cursor"].execute(
                "SELECT summary, open_topics, current_emotion FROM working_memory WHERE user_id=%s",
                (self.user_id,),
            )
            row = db["cursor"].fetchone()
        if not row:
            return None
        return {
            "summary": row["summary"],
            "open_topics": json.loads(row["open_topics"]) if row["open_topics"] else [],
            "current_emotion": row["current_emotion"],
        }

    # 保存工作记忆（upsert）
    def save(self, summary: str, open_topics: list, current_emotion: str | None = None):
        with mysql_db() as db:
            db["cursor"].execute(
                """
                INSERT INTO working_memory(user_id, summary, open_topics, current_emotion)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    summary = VALUES(summary),
                    open_topics = VALUES(open_topics),
                    current_emotion = VALUES(current_emotion)
                """,
                (self.user_id, summary,
                 json.dumps(open_topics[:5], ensure_ascii=False), current_emotion),
            )
