from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer

from app.ai.agent.companion.schema.companion_schema import EmotionSchema
from app.ai.agent.companion.state.companion_state import CompanionState
from app.ai.model.my_model import MyModel
from app.ai.prompt.builder_prompt_yaml import BuilderPromptYaml
from app.common.mysql_db import mysql_db

"""
情感分析节点：识别用户情绪 -> 写入emotion_records表 -> 供对话节点注入
"""
# 读取外部提示词文件
prompt = BuilderPromptYaml.get_prompt("emotion_agent.yaml")

# 情感分析智能体（结构化输出）
emotion_agent = create_agent(
    model=MyModel.get_model(),
    system_prompt=prompt,
    response_format=EmotionSchema,
)


async def emotion_node(state: CompanionState):
    write = get_stream_writer()
    # 推送阶段状态，前端可显示"感受情绪中..."
    write({"stage": "emotion"})

    try:
        rs = await emotion_agent.ainvoke({"messages": [HumanMessage(content=state["question"])]})
        data = rs["structured_response"].model_dump()
    except Exception as e:
        print(f"情感分析异常，降级默认值:{e}")
        data = {"emotion": "平静", "intensity": 5, "is_crisis": False}

    # 情绪记录落库（情感曲线可视化数据源）
    try:
        with mysql_db() as db:
            db["cursor"].execute(
                "INSERT INTO emotion_records(user_id, session_id, emotion, intensity) VALUES(%s,%s,%s,%s)",
                (state["user_id"], state["session_id"], data["emotion"], data["intensity"]),
            )
    except Exception as e:
        print(f"情绪记录落库失败:{e}")

    # 推送情绪结果给前端
    write({"emotion": data})
    return {
        "emotion": data["emotion"],
        "emotion_intensity": data["intensity"],
        "is_crisis": data["is_crisis"],
    }
