from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.ai.memory.save.long_memory import LongMemory
from app.ai.memory.save.profile_memory import ProfileMemory
from app.ai.memory.save.working_memory import WorkingMemory
from app.common.auth import get_current_user
from app.common.mysql_db import mysql_db

memory_router = APIRouter(prefix="/api/memory", tags=["记忆与情感"])


# 长期记忆列表（当前用户）
@memory_router.get("/list")
async def memory_list(user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT memory_id, content, category, importance, created_at FROM long_term_memories "
            "WHERE user_id=%s ORDER BY created_at DESC",
            (user["user_id"],),
        )
        rows = db["cursor"].fetchall()
    return {"code": 200, "msg": "ok", "data": rows}


# 删除长期记忆（MySQL元数据 + Chroma向量）
@memory_router.delete("/{memory_id}")
async def memory_delete(memory_id: str, user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "DELETE FROM long_term_memories WHERE memory_id=%s AND user_id=%s",
            (memory_id, user["user_id"]),
        )
        affected = db["cursor"].rowcount
    if affected == 0:
        return {"code": 500, "msg": "记忆不存在"}
    try:
        LongMemory().delete(memory_id)
    except Exception as e:
        # 元数据已删，向量删除失败不影响前端
        print(f"Chroma向量删除失败:{e}")
    return {"code": 200, "msg": "删除成功"}


# 档案卡 + 工作记忆
@memory_router.get("/profile")
async def profile_get(user: dict = Depends(get_current_user)):
    profile = ProfileMemory(user["user_id"]).query()
    working = WorkingMemory(user["user_id"]).query()
    return {"code": 200, "msg": "ok", "data": {"profile": profile, "working": working}}


class ProfileSchema(BaseModel):
    name: str | None = None
    occupation: str | None = None
    preferences: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)


# 档案卡编辑保存
@memory_router.put("/profile")
async def profile_put(data: ProfileSchema, user: dict = Depends(get_current_user)):
    ProfileMemory(user["user_id"]).save(data.model_dump())
    return {"code": 200, "msg": "保存成功"}


# 情绪曲线数据（最近200条记录）
@memory_router.get("/emotion_curve")
async def emotion_curve(user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT emotion, intensity, created_at FROM emotion_records "
            "WHERE user_id=%s ORDER BY created_at DESC LIMIT 200",
            (user["user_id"],),
        )
        rows = db["cursor"].fetchall()
    rows.reverse()  # 时间正序
    return {"code": 200, "msg": "ok", "data": rows}
