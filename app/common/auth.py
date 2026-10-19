import jwt as pyjwt
from fastapi import Header, HTTPException

from app.common.jwt_util import decode_token
from app.common.redis_util import get_redis


async def get_current_user(authorization: str = Header(None)) -> dict:
    """从 Authorization: Bearer <token> 中解析当前登录用户

    认证流程（参考RAG项目的JWTUtil）：
    1. 解析JWT（签名+过期校验）
    2. 拦截黑名单token（退出登录时白名单转入黑名单）
    3. 校验Redis登录态白名单（jti存在即有效，支持服务端强制下线）
    路由中使用：user: dict = Depends(get_current_user)
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或token缺失")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token已过期，请重新登录")
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="无效token")

    jti = payload.get("jti")
    r = get_redis()
    # 黑名单拦截：已退出登录的token
    if await r.get(f"blacklist_token:{jti}") is not None:
        raise HTTPException(status_code=401, detail="已退出登录，请重新登录")
    # 白名单校验：登录态在Redis中存在才有效
    if await r.get(f"login_token:{jti}") is None:
        raise HTTPException(status_code=401, detail="登录态已失效，请重新登录")
    return {"user_id": payload["user_id"], "username": payload["username"], "jti": jti}
