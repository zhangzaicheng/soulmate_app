import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.ai.agent.companion.schema.companion_schema import WorkingMemorySchema
from app.ai.memory.save.working_memory import WorkingMemory
from app.ai.model.my_model import MyModel
from app.ai.prompt.builder_prompt_yaml import BuilderPromptYaml

"""
工作记忆更新智能体：旧工作记忆 + 本轮对话 -> 更新对用户的整体了解
LLM失败时降级规则更新：工作记忆summary保留，追加本轮情绪
"""
prompt = BuilderPromptYaml.get_prompt("working_memory_agent.yaml")

working_agent = create_agent(
    model=MyModel.get_model(),
    system_prompt=prompt,
    response_format=WorkingMemorySchema,
)


class WorkingAgent:

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.working_memory = WorkingMemory(user_id)

    async def update(self, dialog_text: str, current_emotion: str | None):
        old = self.working_memory.query()
        try:
            user_msg = (
                f"旧工作记忆：{json.dumps(old, ensure_ascii=False) if old else '（无）'}\n\n"
                f"本轮对话：\n{dialog_text}\n\n请输出更新后的工作记忆。"
            )
            rs = await working_agent.ainvoke({"messages": [HumanMessage(content=user_msg)]})
            data = rs["structured_response"].model_dump()
        except Exception as e:
            # 降级：保留旧summary，话题追加本轮，情绪用本轮识别结果
            print(f"工作记忆LLM更新失败，降级规则更新:{e}")
            data = {
                "summary": old["summary"] if old else "",
                "open_topics": (old.get("open_topics", []) if old else []),
                "current_emotion": current_emotion or (old.get("current_emotion") if old else "平静"),
            }
        self.working_memory.save(data["summary"], data["open_topics"], data["current_emotion"])
        return data
