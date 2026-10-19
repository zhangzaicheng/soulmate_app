import os

import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

_redis = None


def get_redis():
    """获取全局异步Redis客户端（单例）"""
    global _redis
    if _redis is None:
        _redis = redis.StrictRedis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=0,
        )
    return _redis
