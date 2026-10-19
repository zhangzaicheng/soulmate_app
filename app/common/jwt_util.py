import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "soulmate_default_secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# token有效期（分钟）
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))


def create_token(user_id: int, username: str) -> str:
    """签发JWT：jti为token唯一标识，登录/注册后由user_service写入Redis登录态白名单"""
    payload = {
        "jti": uuid.uuid4().hex,
        "user_id": user_id,
        "username": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解析JWT，失败时抛出 jwt.PyJWTError"""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
