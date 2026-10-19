from fastapi import APIRouter
from fastapi.responses import RedirectResponse

default_page_router = APIRouter()


@default_page_router.get("/")
async def default_page():
    # 重定向到静态聊天测试页
    return RedirectResponse(url="/static/index.html")
