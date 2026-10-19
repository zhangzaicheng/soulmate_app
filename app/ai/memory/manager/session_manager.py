from app.ai.memory.manager.prompt_builder import PromptBuilder
from app.ai.memory.save.long_memory import LongMemory
from app.ai.memory.save.profile_memory import ProfileMemory
from app.ai.memory.save.summary_memory import SummaryMemory
from app.ai.memory.save.window_memory import WindowMemory
from app.ai.memory.save.working_memory import WorkingMemory


class SessionManager:
    """会话管理器：负责记忆对象的创建和记忆提示词的生成"""

    def __init__(self, session_id: str, user_id: int):
        self.session_id = session_id
        self.user_id = user_id
        self.window_memory = WindowMemory(session_id)
        self.summary_memory = SummaryMemory(session_id)
        self.long_memory = LongMemory()
        self.profile_memory = ProfileMemory(user_id)
        self.working_memory = WorkingMemory(user_id)
        self.prompt_builder = PromptBuilder(session_id, user_id)

    # 添加窗口记忆
    async def save(self, role: str, content: str):
        await self.window_memory.save(role, content)

    # 构建记忆提示词（长期记忆段由图中memory_retrieval节点追加）
    async def build_prompt(self, question: str) -> str:
        return await self.prompt_builder.build(question)
