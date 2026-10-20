from datetime import datetime, timedelta

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


# 音乐陪伴触发参数（阶段五）
NEGATIVE_EMOTIONS = {"焦虑", "愤怒", "难过", "孤独", "委屈", "害怕", "疲惫", "迷茫"}
NEGATIVE_WINDOW = 5          # 统计最近N条情绪记录
NEGATIVE_THRESHOLD = 3       # 负面条数达到该值触发
MUSIC_COOLDOWN_MINUTES = 30  # 距上次推音乐的冷却时间（防连续几轮反复推）


def _check_need_music(user_id: int) -> bool:
    """是否触发音乐陪伴：
    1. 用户音乐开关开启（未设置时默认开启）
    2. 最近5条情绪记录中负面≥3条
    3. 距上次推音乐已超过30分钟
    只由情绪累积触发，不分析对话具体内容
    """
    try:
        with mysql_db() as db:
            # 开关关闭则永不触发
            db["cursor"].execute(
                "SELECT music_enabled FROM user_music_setting WHERE user_id=%s", (user_id,)
            )
            row = db["cursor"].fetchone()
            if row and int(row["music_enabled"]) == 0:
                return False
            # 最近N条情绪中负面条数
            db["cursor"].execute(
                "SELECT emotion FROM emotion_records WHERE user_id=%s "
                "ORDER BY created_at DESC LIMIT %s",
                (user_id, NEGATIVE_WINDOW),
            )
            rows = db["cursor"].fetchall()
            if len(rows) < NEGATIVE_WINDOW:
                return False
            neg = sum(1 for r in rows if r["emotion"] in NEGATIVE_EMOTIONS)
            if neg < NEGATIVE_THRESHOLD:
                return False
            # 冷却期内已推过则跳过
            db["cursor"].execute(
                "SELECT MAX(created_at) AS t FROM music_events WHERE user_id=%s", (user_id,)
            )
            row = db["cursor"].fetchone()
            if row and row["t"]:
                if datetime.now() - row["t"] < timedelta(minutes=MUSIC_COOLDOWN_MINUTES):
                    return False
            return True
    except Exception as e:
        # 表不存在/查询异常一律不触发，保证对话主流程不受影响
        print(f"音乐触发判断失败（不触发音乐）:{e}")
        return False


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

    # 音乐陪伴触发判断（阶段五）：只看情绪累积 + 用户开关，不分析对话内容
    need_music = _check_need_music(state["user_id"])

    # 推送情绪结果给前端
    write({"emotion": data})
    return {
        "emotion": data["emotion"],
        "emotion_intensity": data["intensity"],
        "is_crisis": data["is_crisis"],
        "need_music": need_music,
    }
