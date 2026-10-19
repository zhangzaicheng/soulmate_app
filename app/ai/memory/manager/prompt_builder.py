from app.ai.memory.save.profile_memory import ProfileMemory
from app.ai.memory.save.window_memory import WindowMemory
from app.ai.memory.save.working_memory import WorkingMemory
from app.ai.memory.save.summary_memory import SummaryMemory


class PromptBuilder:
    """记忆提示词构建器：把各层记忆拼成一段注入对话的记忆上下文

    窗口记忆(Redis) + 摘要记忆(PG) + 用户画像(MySQL) + 工作记忆(MySQL)
    长期记忆检索段由 memory_retrieval 节点在图内追加（含bge召回+reranker重排）
    """

    def __init__(self, session_id: str, user_id: int):
        self.window_memory = WindowMemory(session_id)
        self.summary_memory = SummaryMemory(session_id)
        self.profile_memory = ProfileMemory(user_id)
        self.working_memory = WorkingMemory(user_id)
        self.session_id = session_id
        self.user_id = user_id

    # 构建记忆上下文
    async def build(self, question: str) -> str:
        prompt = ""

        # ---------- 工作记忆（跨会话整体了解，始终注入，giftia设计） ----------
        working = self.working_memory.query()
        if working:
            prompt += "【你对用户的整体了解（跨对话持久）】\n"
            if working["summary"]:
                prompt += f"{working['summary']}\n"
            if working["open_topics"]:
                prompt += f"近期可以关心的话题：{'、'.join(working['open_topics'])}\n"

        # ---------- 用户画像 ----------
        profile = self.profile_memory.query()
        if profile and (profile["name"] or profile["occupation"] or profile["preferences"] or profile["relationships"]):
            prompt += "【用户档案】\n"
            if profile["name"]:
                prompt += f"姓名：{profile['name']}\n"
            if profile["occupation"]:
                prompt += f"职业：{profile['occupation']}\n"
            if profile["preferences"]:
                prompt += f"喜好：{'、'.join(profile['preferences'])}\n"
            if profile["relationships"]:
                prompt += f"重要的人/事：{'、'.join(profile['relationships'])}\n"

        # ---------- 摘要记忆（当前会话的历史概括） ----------
        summary = await self.summary_memory.query()
        if summary:
            prompt += f"【之前聊了什么】{summary}\n"

        # ---------- 窗口记忆（近期对话原文） ----------
        window_memory = await self.window_memory.query()
        if window_memory:
            prompt += "【近期对话记录】\n"
            for i in window_memory:
                if i["role"] == "user":
                    prompt += f"用户：{i['content']}\n"
                else:
                    prompt += f"你：{i['content']}\n"
            prompt += "（以上是你和用户最近聊过的话，最近的在最后）\n"

        if not prompt:
            prompt = "【记忆上下文】这是你和用户的第一次对话。\n"
        return prompt
