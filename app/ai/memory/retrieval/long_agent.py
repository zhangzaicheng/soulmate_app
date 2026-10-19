from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.ai.agent.companion.schema.companion_schema import MemoryListSchema
from app.ai.memory.save.long_memory import LongMemory
from app.ai.model.my_model import MyModel
from app.ai.prompt.builder_prompt_yaml import BuilderPromptYaml

"""
长期记忆提取智能体：从本轮对话提取用户事实 -> 写入Chroma(向量) + MySQL(元数据)
"""
prompt = BuilderPromptYaml.get_prompt("memory_save_agent.yaml")

memory_extract_agent = create_agent(
    model=MyModel.get_model(),
    system_prompt=prompt,
    response_format=MemoryListSchema,
)

# 规则提取兜底：LLM失败时按关键词提取
_RULES = ["我叫", "我喜欢", "我讨厌", "我在", "我养", "我家里", "我是", "我的", "我最近", "我打算", "我准备", "我下"]


def _rule_extract(dialog_text: str) -> list[dict]:
    items = []
    for line in dialog_text.replace("。", "\n").replace("！", "\n").replace("？", "\n").split("\n"):
        line = line.strip()
        if any(k in line for k in _RULES) and 5 < len(line) < 60 and line.startswith(("我", "我叫")):
            items.append({"content": line, "category": "fact", "importance": 0.5})
    return items[:3]


class LongAgent:

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.long_memory = LongMemory()

    async def update(self, dialog_text: str):
        # 1. LLM结构化提取
        items = []
        try:
            user_msg = f"请从以下对话中提取值得长期记住的用户事实：\n{dialog_text}"
            rs = await memory_extract_agent.ainvoke({"messages": [HumanMessage(content=user_msg)]})
            items = [m.model_dump() for m in rs["structured_response"].memories]
        except Exception as e:
            print(f"LLM记忆提取失败，降级规则提取:{e}")
        # 2. 兜底：LLM没提取到时用规则
        if not items:
            items = _rule_extract(dialog_text)
        if not items:
            return []
        # 3. 向量本体写Chroma
        self.long_memory.add(items, self.user_id)
        return items
