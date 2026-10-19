import bcrypt
from dotenv import load_dotenv

from app.common.jwt_util import create_token, decode_token, JWT_EXPIRE_MINUTES
from app.common.mysql_db import mysql_db
from app.common.redis_util import get_redis

load_dotenv()

"""
用户服务层（分层结构参考RAG项目的UserService）：
注册 / 登录 / 退出登录
"""


def hash_password(password: str) -> str:
    # 原生bcrypt（与已安装bcrypt==5.0.0兼容，不引入passlib）
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


async def _save_token_whitelist(token: str):
    """登录/注册成功后：token写入Redis登录态白名单，key为jti"""
    jti = decode_token(token)["jti"]
    r = get_redis()
    await r.setex(f"login_token:{jti}", JWT_EXPIRE_MINUTES * 60, token)


# ============================ 注册 ============================
async def register(username: str, password: str, nickname: str, email: str | None):
    with mysql_db() as db:
        # 用户名查重
        db["cursor"].execute("SELECT id FROM users WHERE username=%s", (username,))
        if db["cursor"].fetchone():
            return {"code": 500, "msg": "用户名已存在"}
        # 邮箱查重
        if email:
            db["cursor"].execute("SELECT id FROM users WHERE email=%s", (email,))
            if db["cursor"].fetchone():
                return {"code": 500, "msg": "邮箱已被注册"}
        db["cursor"].execute(
            "INSERT INTO users(username, password_hash, nickname, email) VALUES(%s,%s,%s,%s)",
            (username, hash_password(password), nickname or username, email),
        )
        new_id = db["cursor"].lastrowid
    token = create_token(new_id, username)
    await _save_token_whitelist(token)
    return {"code": 200, "msg": "注册成功", "data": {"token": token, "user_id": new_id, "nickname": nickname or username}}


# ============================ 登录 ============================
async def login(username: str, password: str):
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT id, username, password_hash, nickname FROM users WHERE username=%s",
            (username,),
        )
        row = db["cursor"].fetchone()
    if not row or not check_password(password, row["password_hash"]):
        return {"code": 500, "msg": "用户名或密码错误"}
    token = create_token(row["id"], row["username"])
    await _save_token_whitelist(token)
    return {"code": 200, "msg": "登录成功", "data": {"token": token, "user_id": row["id"], "nickname": row["nickname"]}}


# ============================ 退出登录 ============================
async def logout(payload: dict):
    """白名单中的token整条转入黑名单（参考RAG项目login_out）"""
    jti = payload["jti"]
    r = get_redis()
    key = f"login_token:{jti}"
    ttl = await r.ttl(key)
    token = await r.get(key)
    if ttl and ttl > 0 and token:
        await r.setex(f"blacklist_token:{jti}", ttl, token)
        await r.delete(key)
    return {"code": 200, "msg": "退出登录成功"}
