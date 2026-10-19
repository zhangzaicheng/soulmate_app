import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.ai.memory.save.summary_memory import SummaryMemory
from app.ai.model.my_model import MyModel
from app.ai.prompt.builder_prompt_yaml import BuilderPromptYaml

"""
摘要记忆更新智能体：旧摘要 + 本轮对话 -> 新摘要（LLM增量更新）
"""
prompt = BuilderPromptYaml.get_prompt("summary_agent.yaml")

summary_agent = create_agent(
    model=MyModel.get_model(),
    system_prompt=prompt,
)


class SummaryAgent:

    def __init__(self, session_id: str):
        self.summary_memory = SummaryMemory(session_id)

    async def update(self, dialog_text: str):
        old_summary = await self.summary_memory.query()
        try:
            user_msg = f"旧摘要：{old_summary or '（无）'}\n\n本轮对话：\n{dialog_text}\n\n请输出新的摘要。"
            rs = await summary_agent.ainvoke({"messages": [HumanMessage(content=user_msg)]})
            new_summary = rs["messages"][-1].content
        except Exception as e:
            print(f"摘要更新失败，保留旧摘要:{e}")
            return
        await self.summary_memory.save(new_summary)
        return new_summary
