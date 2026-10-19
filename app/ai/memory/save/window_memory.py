import json
import os

import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()


class WindowMemory:
    """短期记忆-窗口记忆：Redis List保存最近N条对话，自动截断+过期"""

    def __init__(self, session_id: str):
        self.redis = redis.StrictRedis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=0,
        )
        # 窗口保留的消息条数（一问一答=2条）
        self.window_size = int(os.getenv("WINDOW_MEMORY_ROUNDS", "16"))
        self.session_id = session_id
        self.key = f"window_memory:{self.session_id}"
        # 过期时间（秒）
        self.window_limit_time = int(os.getenv("WINDOW_MEMORY_TIME", "86400"))

    # 保存一条记忆
    async def save(self, role: str, content: str):
        data = {"role": role, "content": content}
        # 追加到列表尾部
        await self.redis.rpush(self.key, json.dumps(data, ensure_ascii=False))
        # 只保留窗口内的最后N条
        await self.redis.ltrim(self.key, -self.window_size, -1)
        # 刷新过期时间
        await self.redis.expire(self.key, self.window_limit_time)

    # 提取窗口内全部记忆
    async def query(self):
        if await self.redis.exists(self.key):
            data = await self.redis.lrange(self.key, 0, -1)
            return [json.loads(i) for i in data]
        return []


if __name__ == "__main__":
    import asyncio

    async def test():
        w = WindowMemory("test_001")
        await w.save("user", "你好")
        await w.save("ai", "你好呀，今天过得怎么样？")
        print(await w.query())

    asyncio.run(test())
