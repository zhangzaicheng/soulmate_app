from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.common.auth import get_current_user
from app.common.mysql_db import mysql_db

"""
用户设置：音乐陪伴开关（阶段五）
开关关闭后，即使情绪累积达标也不再播放音乐；只由情绪触发，与对话内容无关
"""
setting_router = APIRouter(prefix="/api/user", tags=["用户设置"])


class MusicSettingSchema(BaseModel):
    music_enabled: bool


# 查询音乐陪伴开关（未设置过默认开启）
@setting_router.get("/music-setting")
async def get_music_setting(user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT music_enabled FROM user_music_setting WHERE user_id=%s",
            (user["user_id"],),
        )
        row = db["cursor"].fetchone()
    # 从未设置过 -> 默认开启
    enabled = bool(row["music_enabled"]) if row else True
    return {"code": 200, "msg": "ok", "data": {"music_enabled": enabled}}


# 设置音乐陪伴开关
@setting_router.put("/music-setting")
async def set_music_setting(data: MusicSettingSchema, user: dict = Depends(get_current_user)):
    flag = int(data.music_enabled)
    with mysql_db() as db:
        db["cursor"].execute(
            "INSERT INTO user_music_setting(user_id, music_enabled) VALUES(%s,%s) "
            "ON DUPLICATE KEY UPDATE music_enabled=%s",
            (user["user_id"], flag, flag),
        )
    return {"code": 200, "msg": "已保存", "data": {"music_enabled": data.music_enabled}}
