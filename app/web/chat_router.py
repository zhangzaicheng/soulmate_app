import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.common.auth import get_current_user

chat_router = APIRouter(prefix="/api/chat", tags=["聊天"])


# 聊天接口（SSE流式）
# 注意：前端必须用fetch读取流（EventSource无法携带Authorization头）
@chat_router.get("")
async def chat(
    request: Request,
    question: str,
    session_id: str,
    user: dict = Depends(get_current_user), # jwt鉴权，从token中解析出user_id
):
    companion_agent = request.app.state.companion_agent

    async def generate(question: str, user_id: int, session_id: str):
        try:
            async for x in companion_agent.chat(question, user_id, session_id):
                yield f"data: {json.dumps(x, ensure_ascii=False)}\n\n" # sse流式输出
            yield f"data: {json.dumps({'type': 'done', 'data': ''}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'data': ''}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(question, user["user_id"], session_id),
        media_type="text/event-stream",
    )


# 新建会话（图智能体负责：MySQL持久化 + Redis注册）
@chat_router.post("/create_session")
async def create_session(request: Request, user: dict = Depends(get_current_user)):
    companion_agent = request.app.state.companion_agent
    session_id = await companion_agent.create_session(user["user_id"])
    return {"code": 200, "msg": "新建会话", "data": session_id}
