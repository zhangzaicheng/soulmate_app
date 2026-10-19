from typing import Annotated, TypedDict
import operator

from langchain_core.messages import AnyMessage


class CompanionState(TypedDict):
    """情感陪伴图的状态"""
    # 消息列表：节点返回增量，operator.add自动归并（exam_app同款）
    messages: Annotated[list[AnyMessage], operator.add]
    # 业务字段：直接覆盖
    user_id: int
    session_id: str
    question: str
    # SessionManager构建的记忆上下文（进图前生成）
    memory_prompt: str
    # emotion_node 输出
    emotion: str
    emotion_intensity: int
    is_crisis: bool
    # dialogue_node 输出
    ai_answer: str
