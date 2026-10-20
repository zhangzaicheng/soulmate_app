import asyncio
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import redis.asyncio as redis
import uvicorn

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.ai.agent.care.scheduler import ensure_care_tables, start_scheduler
from app.ai.agent.companion.graph.companion_graph import CompanionGraphAgent
from app.ai.agent.companion.node.music_recommendation_node import ensure_music_tables
from app.ai.memory.save.summary_memory import close_pool, open_pool
from app.web.care_router import care_router
from app.web.chat_router import chat_router
from app.web.default_page_router import default_page_router
from app.web.memory_router import memory_router
from app.web.session_router import session_router
from app.web.setting_router import setting_router
from app.web.user_router import user_router

load_dotenv()
DB_URI = os.getenv("POSTGRESQL_URL")
# 项目根目录（CDN文件已本地化，存放在 app/html 下）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(ROOT, "app", "html")


# 应用生命周期：启动时建立PostgreSQL检查点 + Redis客户端并创建智能体；关闭时释放
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncPostgresSaver.from_conn_string(DB_URI) as saver:
        await saver.setup()  # 幂等，首次运行自动建检查点表
        # 摘要记忆连接池 + 幂等建表
        await open_pool()
        # 预热本地模型（bge向量/重排，首次加载较慢，放启动时避免首请求卡顿）
        try:
            from app.ai.model.my_model import MyModel

            MyModel.get_embedding()
            MyModel.get_reranker()
            print("本地向量/重排模型预热完成")
        except Exception as e:
            print(f"本地模型预热失败:{e}")
        r = redis.StrictRedis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=0,
        )
        app.state.companion_agent = CompanionGraphAgent(saver, r)
        print("情感陪伴智能体创建成功")
        # 主动关心：建表 + 启动定时调度器
        ensure_care_tables()
        start_scheduler()
        # 音乐陪伴建表
        ensure_music_tables()
        yield
    # 清理资源
    app.state.companion_agent = None
    await close_pool()
    print("情感陪伴智能体已释放，PostgreSQL连接池已关闭")


app = FastAPI(lifespan=lifespan)

# 配置静态资源访问目录
# /static 是 URL 访问前缀（不是文件夹名），指向 app/html
app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)

# 注册路由
app.include_router(user_router)
app.include_router(setting_router)
app.include_router(session_router)
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(care_router)
app.include_router(default_page_router)

if __name__ == "__main__":
    # Windows下必须切换为SelectorEventLoop，否则psycopg异步驱动报错
    # 注意事项：仅当本文件作为 __main__ 运行时生效（IDE 点运行 / python app/main.py）
    #          用 python -m uvicorn app.main:app 外部启动时，main.py是被import的，__main__块不执行
    #          此时需依赖 uvicorn --reload 自动切SelectorEventLoop，或命令行加 --loop asyncio:SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # 启动方式一（推荐）：PyCharm 右上角选中 soulmate_app 配置，点运行
    # 启动方式二（终端，需在项目根目录执行）：python -m uvicorn app.main:app --reload --port 8000
    #   注意是 python -m：-m 会把cwd（项目根）加入sys.path，app包才能被找到
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, loop="asyncio:SelectorEventLoop")
