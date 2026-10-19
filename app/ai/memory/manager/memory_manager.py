from app.ai.memory.retrieval.long_agent import LongAgent
from app.ai.memory.retrieval.profile_agent import ProfileAgent
from app.ai.memory.retrieval.summary_agent import SummaryAgent
from app.ai.memory.retrieval.working_agent import WorkingAgent


class MemoryManager:
    """记忆更新调度器：对话结束后统一更新摘要/长期/画像/工作记忆（后台异步执行）"""

    def __init__(self, session_id: str, user_id: int):
        self.session_id = session_id
        self.user_id = user_id

    async def update(self, question: str, ai_answer: str, emotion: str):
        dialog_text = f"用户：{question}\n你：{ai_answer}"

        # 1. 摘要记忆（PG，会话级）
        try:
            summary_agent = SummaryAgent(self.session_id)
            await summary_agent.update(dialog_text)
        except Exception as e:
            print(f"摘要记忆更新异常:{e}")

        # 2. 长期记忆（Chroma + MySQL，用户级事实提取）
        try:
            long_agent = LongAgent(self.user_id)
            items = await long_agent.update(dialog_text)
            if items:
                print(f"长期记忆新增{len(items)}条: {[i['content'] for i in items]}")
        except Exception as e:
            print(f"长期记忆更新异常:{e}")

        # 3. 用户画像（MySQL，结构化提取）
        try:
            profile_agent = ProfileAgent(self.user_id)
            await profile_agent.update(dialog_text)
        except Exception as e:
            print(f"画像更新异常:{e}")

        # 4. 工作记忆（MySQL，跨会话整体了解）
        try:
            working_agent = WorkingAgent(self.user_id)
            await working_agent.update(dialog_text, emotion)
        except Exception as e:
            print(f"工作记忆更新异常:{e}")
