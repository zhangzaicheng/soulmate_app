from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.common.auth import get_current_user
from app.common.mysql_db import mysql_db
from app.web import user_service

user_router = APIRouter(prefix="/api/user", tags=["用户"])


class RegisterSchema(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=50)
    nickname: str = Field(default="", max_length=50)
    email: str | None = Field(default=None, max_length=100)


class LoginSchema(BaseModel):
    username: str
    password: str


# 注册（成功即登录，返回token）
@user_router.post("/register")
async def register(user: RegisterSchema):
    return await user_service.register(user.username, user.password, user.nickname, user.email)


# 登录
@user_router.post("/login")
async def login(user: LoginSchema):
    return await user_service.login(user.username, user.password)


# 退出登录（token转入Redis黑名单）
@user_router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    return await user_service.logout(user)


# 当前用户信息
@user_router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT id, username, nickname, email, avatar FROM users WHERE id=%s",
            (user["user_id"],),
        )
        row = db["cursor"].fetchone()
    if not row:
        return {"code": 500, "msg": "用户不存在"}
    return {"code": 200, "msg": "ok", "data": row}
