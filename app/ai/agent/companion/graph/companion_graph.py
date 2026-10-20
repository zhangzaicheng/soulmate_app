import contextlib
import json
import time
import uuid

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from app.ai.agent.companion.node.dialogue_node import dialogue_node
from app.ai.agent.companion.node.emotion_node import emotion_node
from app.ai.agent.companion.node.memory_retrieval_node import memory_retrieval_node
from app.ai.agent.companion.node.memory_save_node import memory_save_node
from app.ai.agent.companion.node.music_recommendation_node import music_recommendation_node
from app.ai.agent.companion.state.companion_state import CompanionState
from app.ai.memory.manager.session_manager import SessionManager
from app.common.mysql_db import mysql_db


def _route_after_emotion(state: CompanionState) -> str:
    """emotion之后的路由函数（阶段五条件分支）：
    need_music=True  -> 插入 music_recommendation 节点（音乐陪伴选曲）
    need_music=False -> 直接走 memory_retrieval
    """
    return "music" if state.get("need_music") else "memory"


"""
情感陪伴智能体：
图结构（阶段五）：
    START -> emotion（情感分析 + 音乐触发判断）
          -> [条件分支] need_music=True  -> music_recommendation（音乐陪伴选曲）
                       need_music=False -> 直接到 memory_retrieval
          -> memory_retrieval（长期记忆检索）-> dialogue（对话生成）
          -> memory_save（记忆保存+后台记忆更新）-> END
业务数据持久化在 MySQL（会话/消息/情绪/画像/工作记忆/长期记忆元数据），
摘要记忆在 PostgreSQL，长期记忆向量在 Chroma，图状态由 PostgreSQL checkpointer 保存。
音乐陪伴（阶段五）由情绪累积触发，音乐不写入messages，不污染对话历史与记忆系统。
"""


class CompanionGraphAgent:

    def __init__(self, checkpoint, redis):
        self.memory = checkpoint
        self.redis = redis
        self.agent = self.get_agent()

    # 构建图
    def get_agent(self):
        graph = StateGraph(CompanionState)
        # 添加节点
        graph.add_node("emotion", emotion_node)
        graph.add_node("music_recommendation", music_recommendation_node)
        graph.add_node("memory_retrieval", memory_retrieval_node)
        graph.add_node("dialogue", dialogue_node)
        graph.add_node("memory_save", memory_save_node)
        # 入口固定
        graph.add_edge(START, "emotion")
        # 阶段五：emotion后条件分支，负面情绪达阈值时插入音乐推荐
        graph.add_conditional_edges(
            "emotion",
            _route_after_emotion,
            {"music": "music_recommendation", "memory": "memory_retrieval"},
        )
        # 音乐推荐完成后汇合到记忆检索
        graph.add_edge("music_recommendation", "memory_retrieval")
        graph.add_edge("memory_retrieval", "dialogue")
        graph.add_edge("dialogue", "memory_save")
        graph.add_edge("memory_save", END)
        # 编译，检查点持久化到PostgreSQL
        self.agent = graph.compile(checkpointer=self.memory)
        return self.agent

    # 画图（答辩展示用，生成图结构PNG）
    def draw(self):
        data = self.agent.get_graph().draw_mermaid_png()
        with open("陪伴图.png", "wb") as f:
            f.write(data)
        print("图片已保存:陪伴图.png")

    # 会话创建（MySQL持久化 + Redis注册）
    async def create_session(self, user_id: int, title: str = "新的对话") -> str:
        session_id = uuid.uuid4().hex
        with mysql_db() as db:
            db["cursor"].execute(
                "INSERT INTO conversations(session_id, user_id, title) VALUES(%s,%s,%s)",
                (session_id, user_id, title),
            )
        # Redis注册（24小时过期，仅作为存在性缓存；真实归属以MySQL为准）
        if self.redis:
            data = {"user_id": user_id, "create_time": time.time()}
            await self.redis.set(f"session:{session_id}", json.dumps(data), ex=60 * 60 * 24)
        return session_id

    """
    检查会话：会话是否存在 + 是否归属该用户（以MySQL为准）
    """
    async def check_session(self, user_id: int, session_id: str):
        if not session_id:
            return False, "会话id为空"
        with mysql_db() as db:
            db["cursor"].execute(
                "SELECT user_id FROM conversations WHERE session_id=%s", (session_id,)
            )
            row = db["cursor"].fetchone()
        if not row:
            return False, "会话不存在"
        if row["user_id"] != user_id:
            return False, "会话不属于该用户"
        # 刷新Redis注册（过期后自动续期）
        data = {"user_id": user_id, "create_time": time.time()}
        await self.redis.set(f"session:{session_id}", json.dumps(data), ex=60 * 60 * 24)
        return True, "会话存在且归属该用户"

    # 对话（SSE流式）
    async def chat(self, question: str, user_id: int, session_id: str):
        # 1. 校验会话存在 + 归属匹配
        ok, reason = await self.check_session(user_id, session_id)
        if not ok:
            yield {"type": "error", "data": reason}
            return

        # ---------------------添加记忆---------------------
        session_manager = SessionManager(session_id, user_id)
        # 用户消息进窗口记忆
        await session_manager.save("user", question)
        # 构建记忆上下文提示词
        memory_prompt = await session_manager.build_prompt(question)

        # 记录AI回复
        ai_answer = ""
        # 构建图输入
        user_msg = {
            "messages": [{"role": "system", "content": memory_prompt}, HumanMessage(content=question)],
            "user_id": user_id,
            "session_id": session_id,
            "question": question,
            "memory_prompt": memory_prompt,
            "emotion": "平静",
            "emotion_intensity": 5,
            "is_crisis": False,
            # 音乐陪伴（阶段五）默认值，由emotion_node判断是否置为True
            "need_music": False,
            "music_recommendation": {},
            "ai_answer": "",
        }
        # 配置检查点：thread_id绑定会话
        config = {"configurable": {"thread_id": session_id}}

        try:
            async with self._session_lock(session_id):
                print(f"开始处理会话:{session_id}")
                # 只使用custom通道：dialogue节点内部流式write的token
                # （不能使用messages通道，否则节点返回的完整AIMessage会导致内容重复）
                async for m in self.agent.astream(
                    user_msg, config, stream_mode="custom"
                ):
                    # custom事件：{"stage":...} / {"emotion":...} / {"music":...} / token字符串
                    if isinstance(m, dict):
                        if "stage" in m:
                            yield {"type": "status", "data": m["stage"]}
                        elif "emotion" in m:
                            yield {"type": "emotion", "data": m["emotion"]}
                        elif "music" in m:
                            # 音乐陪伴：把选中的音乐推给前端<audio>播放
                            yield {"type": "music", "data": m["music"]}
                    elif isinstance(m, str):
                        ai_answer += m
                        yield {"type": "token", "data": m}
            print(f"AI回复:{ai_answer}")
        except Exception as e:
            print(f"错误:{e}")
            yield {"type": "error", "data": str(e)}
            return

        # ---------------------更新记忆---------------------
        # AI回复进窗口记忆
        await session_manager.save("ai", ai_answer)
        # 阶段二将在此追加：MemoryManager.update()（摘要/长期/画像/工作记忆更新）

    """
    会话锁：同一session同一时刻只允许一个请求进入
    """
    @contextlib.asynccontextmanager
    async def _session_lock(self, session_id: str):
        key = f"lock:session:{session_id}"
        # 随机token，防止误删他人的锁
        token = uuid.uuid4().hex
        # nx=True：只有key不存在时才设置成功；px为毫秒过期时间
        ok = await self.redis.set(key, token, nx=True, px=5 * 60 * 1000)
        if not ok:
            raise RuntimeError("会话忙，请稍后再试")
        try:
            yield
        finally:
            # Lua脚本原子释放锁，只删自己的锁
            lua = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """
            try:
                await self.redis.eval(lua, 1, key, token)
            except Exception:
                pass


if __name__ == "__main__":
    # 画图
    from langgraph.checkpoint.memory import InMemorySaver

    agent = CompanionGraphAgent(InMemorySaver(), None)
    agent.draw()

    # 对话测试（需redis + MySQL）
    # import asyncio
    # async def test():
    #     import redis.asyncio as redis
    #     r = redis.StrictRedis(host="localhost", port=6379, db=0)
    #     agent = CompanionGraphAgent(InMemorySaver(), r)
    #     session_id = await agent.create_session(1)
    #     print(f"会话:{session_id}")
    #     async for x in agent.chat("今天心情不太好，工作好累", 1, session_id):
    #         print(x)
    # asyncio.run(test())
