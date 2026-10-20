import os
import random

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer

from app.ai.agent.companion.schema.companion_schema import MusicPickSchema
from app.ai.agent.companion.state.companion_state import CompanionState
from app.ai.model.my_model import MyModel
from app.ai.prompt.builder_prompt_yaml import BuilderPromptYaml
from app.common.mysql_db import mysql_db

"""
音乐推荐节点（阶段五）：
用户负面情绪累积达到阈值时，由音乐选曲智能体（LLM）根据用户当前情绪、刚说的话，
以及音乐库中每首歌的场景化描述，挑选最合适的一首，把音乐URL推给前端 <audio> 播放。
LLM 不可用或返回了库外的文件名时，自动回退到情绪标签匹配 + 随机。
音乐不写入 messages，不进入对话历史/长期记忆/摘要记忆，不污染记忆系统。
"""

# 本文件位于 app/ai/agent/companion/node/，向上5级到 app/
_APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
# 音乐库配置（音乐文件目录与 /static/music/ 共享，由前端 audio 标签加载）
LIBRARY_PATH = os.path.join(_APP_DIR, "ai", "prompt", "music_library.yaml")

# 音乐选曲提示词（五段式）
music_prompt = BuilderPromptYaml.get_prompt("music_agent.yaml")

# 音乐选曲智能体（结构化输出：file + reason）
music_agent = create_agent(
    model=MyModel.get_model(),
    system_prompt=music_prompt,
    response_format=MusicPickSchema,
)

_library_cache = None


def ensure_music_tables():
    """幂等建表（应用启动时调用）：用户音乐开关 + 音乐播放事件"""
    with mysql_db() as db:
        db["cursor"].execute("""
            CREATE TABLE IF NOT EXISTS user_music_setting (
                user_id       INT PRIMARY KEY,
                music_enabled TINYINT DEFAULT 1 COMMENT '1=开启 0=关闭',
                updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB COMMENT='用户音乐陪伴开关'
        """)
        db["cursor"].execute("""
            CREATE TABLE IF NOT EXISTS music_events (
                id         BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id    INT NOT NULL,
                session_id VARCHAR(64),
                emotion    VARCHAR(20) COMMENT '触发时的情绪标签',
                music_name VARCHAR(100),
                music_file VARCHAR(255),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                KEY idx_user (user_id)
            ) ENGINE=InnoDB COMMENT='音乐陪伴播放事件（不污染对话历史）'
        """)


def _load_library() -> list:
    """加载音乐库配置（带缓存，避免每轮读文件）"""
    global _library_cache
    if _library_cache is None:
        try:
            import yaml

            with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
                _library_cache = yaml.safe_load(f).get("music", []) or []
        except Exception as e:
            print(f"音乐库加载失败:{e}")
            _library_cache = []
    return _library_cache


async def _pick_by_llm(library: list, emotion: str, user_msg: str):
    """智能体选曲：返回 (选中的曲目dict, 推荐理由)
    失败（异常 或 返回了库中不存在的file）返回 (None, "")，由调用方回退
    """
    try:
        # 把每首歌的场景化描述拼给LLM，让它像真人DJ一样挑选
        lib_text = "\n\n".join(
            f"《{m.get('name', '')}》 file={m['file']}\n  适用场景：{m.get('desc', '').strip()}"
            for m in library
        )
        prompt = (
            f"用户当前情绪：{emotion}\n"
            f"用户刚才说：{user_msg[:150]}\n\n"
            f"候选音乐库：\n{lib_text}\n\n"
            f"请选出最合适的一首。"
        )
        rs = await music_agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
        pick = rs["structured_response"].model_dump()
        # 二次校验：LLM必须选库中存在的file，防止幻觉导致前端404
        valid = [m for m in library if m["file"] == pick.get("file")]
        if valid:
            return valid[0], pick.get("reason", "")
        print(f"LLM选曲返回了库中不存在的file({pick.get('file')})，回退标签匹配")
    except Exception as e:
        print(f"LLM选曲异常，回退标签匹配:{e}")
    return None, ""


async def music_recommendation_node(state: CompanionState):
    write = get_stream_writer()
    # 推送阶段状态，前端可显示"欧若拉正在为你选一首歌..."
    write({"stage": "music"})
    try:
        emotion = state.get("emotion", "")
        user_msg = state.get("question", "")
        library = _load_library()
        if not library:
            return {"music_recommendation": {}}

        # 智能体根据场景描述选曲；失败则回退到情绪标签匹配 + 随机
        pick_obj, reason = await _pick_by_llm(library, emotion, user_msg)
        if pick_obj is None:
            matched = [m for m in library if emotion in (m.get("tags") or [])]
            pick_obj = random.choice(matched or library)

        # 卡片只展示描述首句（完整描述是给LLM选曲用的，太长不适合UI）
        full_desc = pick_obj.get("desc", "").strip()
        short_desc = full_desc.split("\n")[0] if full_desc else ""

        rec = {
            "name": pick_obj.get("name", ""),
            "url": f"/static/music/{pick_obj['file']}",
            "desc": short_desc,
            "emotion": emotion,
            "reason": reason,
        }
        # 推custom通道：前端<audio>播放 + 展示音乐卡片（含选曲理由）
        write({"music": rec})
        return {"music_recommendation": rec}
    except Exception as e:
        print(f"音乐推荐节点异常（不影响对话）:{e}")
        return {"music_recommendation": {}}
