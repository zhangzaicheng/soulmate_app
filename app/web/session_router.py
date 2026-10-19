from fastapi import APIRouter, Depends

from app.common.auth import get_current_user
from app.common.mysql_db import mysql_db

session_router = APIRouter(prefix="/api/session", tags=["会话"])


# 会话列表
@session_router.get("/list")
async def session_list(user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT session_id, title, created_at, updated_at FROM conversations "
            "WHERE user_id=%s ORDER BY updated_at DESC",
            (user["user_id"],),
        )
        rows = db["cursor"].fetchall()
    return {"code": 200, "msg": "ok", "data": rows}


# 会话内历史消息（前端回显，从MySQL读取）
@session_router.get("/{session_id}/messages")
async def session_messages(session_id: str, user: dict = Depends(get_current_user)):
    # 校验会话归属
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT session_id FROM conversations WHERE session_id=%s AND user_id=%s",
            (session_id, user["user_id"]),
        )
        if not db["cursor"].fetchone():
            return {"code": 500, "msg": "会话不存在或不属于当前用户"}
        db["cursor"].execute(
            "SELECT role, content, emotion, created_at FROM messages "
            "WHERE session_id=%s ORDER BY id ASC",
            (session_id,),
        )
        rows = db["cursor"].fetchall()
    return {"code": 200, "msg": "ok", "data": rows}


# 重命名会话
@session_router.put("/{session_id}/title")
async def rename_session(session_id: str, title: str, user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "UPDATE conversations SET title=%s WHERE session_id=%s AND user_id=%s",
            (title, session_id, user["user_id"]),
        )
        affected = db["cursor"].rowcount
    if affected == 0:
        return {"code": 500, "msg": "会话不存在或不属于当前用户"}
    return {"code": 200, "msg": "重命名成功"}


# 删除会话（连带消息）
@session_router.delete("/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT session_id FROM conversations WHERE session_id=%s AND user_id=%s",
            (session_id, user["user_id"]),
        )
        if not db["cursor"].fetchone():
            return {"code": 500, "msg": "会话不存在或不属于当前用户"}
        db["cursor"].execute("DELETE FROM messages WHERE session_id=%s", (session_id,))
        db["cursor"].execute("DELETE FROM conversations WHERE session_id=%s", (session_id,))
    return {"code": 200, "msg": "删除成功"}
