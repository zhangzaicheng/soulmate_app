import json

from app.common.mysql_db import mysql_db


class ProfileMemory:
    """用户画像：MySQL user_profiles表（结构化信息由ProfileAgent提取后upsert）"""

    def __init__(self, user_id: int):
        self.user_id = user_id

    # 查询画像（返回dict，无画像返回None）
    def query(self) -> dict | None:
        with mysql_db() as db:
            db["cursor"].execute(
                "SELECT name, occupation, preferences, relationships FROM user_profiles WHERE user_id=%s",
                (self.user_id,),
            )
            row = db["cursor"].fetchone()
        if not row:
            return None
        return {
            "name": row["name"],
            "occupation": row["occupation"],
            "preferences": json.loads(row["preferences"]) if row["preferences"] else [],
            "relationships": json.loads(row["relationships"]) if row["relationships"] else [],
        }

    # 保存画像（upsert）
    def save(self, profile: dict):
        with mysql_db() as db:
            db["cursor"].execute(
                """
                INSERT INTO user_profiles(user_id, name, occupation, preferences, relationships)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    occupation = VALUES(occupation),
                    preferences = VALUES(preferences),
                    relationships = VALUES(relationships)
                """,
                (
                    self.user_id,
                    profile.get("name"),
                    profile.get("occupation"),
                    json.dumps(profile.get("preferences") or [], ensure_ascii=False),
                    json.dumps(profile.get("relationships") or [], ensure_ascii=False),
                ),
            )
