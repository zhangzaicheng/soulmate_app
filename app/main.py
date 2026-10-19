import asyncio
import os
import sys
from contextlib import asynccontextmanager

# 把项目根目录加入sys.path（保证 python app/main.py 直接启动时 from app.xxx import 可用）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Windows下必须切换为SelectorEventLoop，否则psycopg异步驱动报错
# （uvicorn仅在--reload模式下会自动切换，这里在模块顶层显式设置，任何启动方式都生效）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import redis.asyncio as redis
import uvicorn

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.ai.agent.care.scheduler import ensure_care_tables, start_scheduler
from app.ai.agent.companion.graph.companion_graph import CompanionGraphAgent
from app.ai.memory.save.summary_memory import close_pool, open_pool
from app.web.care_router import care_router
from app.web.chat_router import chat_router
from app.web.default_page_router import default_page_router
from app.web.memory_router import memory_router
from app.web.session_router import session_router
from app.web.user_router import user_router

load_dotenv()
DB_URI = os.getenv("POSTGRESQL_URL")
# 前端静态资源目录（Vue3 + Element Plus，CDN文件已本地化）
# 基于ROOT拼绝对路径，不受启动目录影响
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
            print(f"本地模型预热失败（对话不受影响，检索会降级）:{e}")
        r = redis.StrictRedis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=0,
        )
        app.state.companion_agent = CompanionGraphAgent(saver, r)
        print("情感陪伴智能体创建成功")
        # 阶段四：主动关心/纪念日建表 + 启动定时任务调度器
        ensure_care_tables()
        start_scheduler()
        yield
    # 消耗对象
    app.state.companion_agent = None
    await close_pool()
    print("情感陪伴智能体已释放，PostgreSQL连接池已关闭")


app = FastAPI(lifespan=lifespan)

# 配置静态资源访问目录
app.mount(
    # 这个/static指的不是static文件夹，而是访问StaticFiles放行的文件夹路径
    "/static",                          # 静态资源访问的前缀 --- 请求路径
    StaticFiles(directory=STATIC_DIR),  # 静态资源目录 --- 放行文件夹
    name="static",                      # 静态资源访问的模块名称
)

# 注册路由
app.include_router(user_router)
app.include_router(session_router)
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(care_router)
app.include_router(default_page_router)

if __name__ == "__main__":
    # 同进程启动：显式指定SelectorEventLoop工厂（uvicorn 0.38在Windows非reload模式下
    # 默认强制ProactorEventLoop，会导致psycopg异步驱动报错）
    # 日常开发也可以从项目根目录运行：python -m uvicorn app.main:app --reload --port 8000
    # （reload模式uvicorn会自动使用SelectorEventLoop）
    sys.path.insert(0, ROOT)  # 保证字符串导入 app.main:app 时能找到app包
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, loop="asyncio:SelectorEventLoop")
