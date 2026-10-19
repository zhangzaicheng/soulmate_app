from langgraph.config import get_stream_writer

from app.ai.agent.companion.state.companion_state import CompanionState
from app.ai.memory.save.long_memory import LongMemory

"""
长期记忆检索节点：bge向量召回 -> bge-reranker重排 -> 追加进记忆上下文
"""
long_memory = LongMemory()


async def memory_retrieval_node(state: CompanionState):
    write = get_stream_writer()
    # 推送阶段状态，前端可显示"回忆中..."
    write({"stage": "retrieval"})

    recalled = []
    try:
        # 向量召回10条 + 重排取top4
        recalled = long_memory.query_with_rerank(
            state["user_id"], state["question"], recall_n=10, top_k=4
        )
    except Exception as e:
        print(f"长期记忆检索失败:{e}") # 不会影响对话

    memory_prompt = state["memory_prompt"]
    if recalled:
        memory_prompt += "【你记得的关于用户的事】\n" + "\n".join(f"- {m}" for m in recalled) + "\n"
        print(f"长期记忆命中{len(recalled)}条: {recalled}")

    # 覆盖memory_prompt，dialogue节点使用完整版
    return {"memory_prompt": memory_prompt}
