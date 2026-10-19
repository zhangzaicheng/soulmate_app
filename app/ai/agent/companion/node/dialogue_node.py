from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.config import get_stream_writer

from app.ai.agent.companion.state.companion_state import CompanionState
from app.ai.model.my_model import MyModel
from app.ai.prompt.builder_prompt_yaml import BuilderPromptYaml

"""
对话生成节点：注入记忆上下文 + 情绪状态 -> 流式生成回复
token流通过get_stream_writer写入custom通道，由SSE转发给前端
"""
# 人设提示词（含防幻觉铁律+危机干预）
persona_prompt = BuilderPromptYaml.get_prompt("persona_dialogue.yaml")

# 正常处理
agent01 = create_agent(
    model=MyModel.get_model(),
    system_prompt=persona_prompt,
    middleware=[
        ModelCallLimitMiddleware(
            thread_limit=3,
            exit_behavior="end",
        ),
    ],
)
# 降级处理
agent02 = create_agent(
    model=MyModel.get_model(),
    system_prompt=persona_prompt,
)


def build_system_prompt(state: CompanionState) -> str:
    """组装完整system prompt：记忆上下文 + 情绪状态 + 危机干预指令"""
    system = state["memory_prompt"]

    # 注入用户当前情绪（giftia的情绪记忆设计）
    system += f"\n【用户当前情绪】{state['emotion']}（强度{state['emotion_intensity']}/10），回复时要注意贴合这个情绪状态。"

    # 危机干预：检测到自伤倾向时追加干预指令
    if state["is_crisis"]:
        system += (
            "\n【紧急】系统检测到用户可能有自伤或轻生的念头，本次回复必须："
            "先温柔地表达关心和陪伴，认真建议用户拨打心理援助热线400-161-9995，"
            "告诉他自己很重要、你一直在。不要说教，不要轻描淡写。"
        )
    return system


async def dialogue_node(state: CompanionState):
    write = get_stream_writer()
    write({"stage": "dialogue"})

    # 组装输入：记忆上下文system + 用户问题
    user_msg = {"messages": [
        SystemMessage(content=build_system_prompt(state)),
        HumanMessage(content=state["question"]),
    ]}
    result = []
    try:
        # 异步流式，token写入custom通道
        async for c, m in agent01.astream(user_msg, stream_mode="messages"):
            if c.content:
                result.append(c.content)
                write(c.content)
        ai_answer = "".join(result)
    except Exception as e:
        # 如果因为中间件限流的原因无法正常输出，就会换为agent02（无中间件限制状态）进行输出
        print(f"=====大模型降级处理:{e}=====")
        result = []
        try:
            async for c, m in agent02.astream(user_msg, stream_mode="messages"):
                if c.content:
                    result.append(c.content)
                    write(c.content)
            ai_answer = "".join(result)
        except Exception as e:
            print(f"=====超时:{e}=====")
            ai_answer = "刚才有点走神了，可以再说一遍吗？"

    # messages归并存入checkpointer，ai_answer供记忆保存节点使用
    return {"messages": [AIMessage(content=ai_answer)], "ai_answer": ai_answer}
