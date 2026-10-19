import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.ai.agent.care.care_agent import generate_care_message
from app.ai.agent.care.scheduler import _save_proactive_message
from app.common.auth import get_current_user
from app.common.mysql_db import mysql_db

care_router = APIRouter(prefix="/api/care", tags=["主动关心"])


# 未读主动消息（前端30秒轮询）
@care_router.get("/unread")
async def unread(user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT id, kind, content, created_at FROM proactive_messages "
            "WHERE user_id=%s AND is_read=0 ORDER BY created_at DESC",
            (user["user_id"],),
        )
        rows = db["cursor"].fetchall()
    return {"code": 200, "msg": "ok", "data": rows}


# 全部已读
@care_router.post("/read_all")
async def read_all(user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "UPDATE proactive_messages SET is_read=1 WHERE user_id=%s", (user["user_id"],)
        )
    return {"code": 200, "msg": "已全部标记已读"}


# 手动触发一次主动关心（演示/测试用）
@care_router.post("/trigger")
async def trigger(user: dict = Depends(get_current_user)):
    content = await generate_care_message(user["user_id"])
    _save_proactive_message(user["user_id"], "care", content)
    return {"code": 200, "msg": "ok", "data": {"content": content}}


# ---------- 纪念日管理 ----------
@care_router.get("/memorials")
async def memorial_list(user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT id, title, date_str, repeat_yearly FROM memorial_days "
            "WHERE user_id=%s ORDER BY date_str",
            (user["user_id"],),
        )
        rows = db["cursor"].fetchall()
    return {"code": 200, "msg": "ok", "data": rows}


class MemorialSchema(BaseModel):
    title: str = Field(max_length=100)
    # MM-DD（每年重复）或 YYYY-MM-DD（单次）
    date_str: str = Field(pattern=r"^\d{2}-\d{2}$|^\d{4}-\d{2}-\d{2}$")
    repeat_yearly: bool = True


@care_router.post("/memorials")
async def memorial_add(data: MemorialSchema, user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "INSERT INTO memorial_days(user_id, title, date_str, repeat_yearly) VALUES(%s,%s,%s,%s)",
            (user["user_id"], data.title, data.date_str, int(data.repeat_yearly)),
        )
    return {"code": 200, "msg": "添加成功"}


@care_router.delete("/memorials/{memorial_id}")
async def memorial_delete(memorial_id: int, user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "DELETE FROM memorial_days WHERE id=%s AND user_id=%s",
            (memorial_id, user["user_id"]),
        )
        affected = db["cursor"].rowcount
    if affected == 0:
        return {"code": 500, "msg": "纪念日不存在"}
    return {"code": 200, "msg": "删除成功"}
