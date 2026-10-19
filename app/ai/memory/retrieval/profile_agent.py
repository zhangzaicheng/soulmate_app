import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.ai.agent.companion.schema.companion_schema import ProfileSchema
from app.ai.memory.save.profile_memory import ProfileMemory
from app.ai.model.my_model import MyModel
from app.ai.prompt.builder_prompt_yaml import BuilderPromptYaml

"""
用户画像更新智能体：旧画像 + 本轮对话 -> 新画像（结构化提取后upsert MySQL）
"""
prompt = BuilderPromptYaml.get_prompt("profile_agent.yaml")

profile_agent = create_agent(
    model=MyModel.get_model(),
    system_prompt=prompt,
    response_format=ProfileSchema,
)


class ProfileAgent:

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.profile_memory = ProfileMemory(user_id)

    async def update(self, dialog_text: str):
        old_profile = self.profile_memory.query()
        try:
            user_msg = (
                f"旧画像：{json.dumps(old_profile, ensure_ascii=False) if old_profile else '（无）'}\n\n"
                f"本轮对话：\n{dialog_text}\n\n请输出合并后的完整画像。"
            )
            rs = await profile_agent.ainvoke({"messages": [HumanMessage(content=user_msg)]})
            new_profile = rs["structured_response"].model_dump()
        except Exception as e:
            print(f"画像更新失败:{e}")
            return
        self.profile_memory.save(new_profile)
        return new_profile
