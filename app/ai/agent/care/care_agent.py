from datetime import datetime

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.ai.memory.save.profile_memory import ProfileMemory
from app.ai.memory.save.working_memory import WorkingMemory
from app.ai.model.my_model import MyModel
from app.ai.prompt.builder_prompt_yaml import BuilderPromptYaml

"""
主动关心/纪念日提醒消息生成：汇总工作记忆+画像+近期情绪+距离上次聊天天数 -> LLM生成一条自然消息
"""
prompt = BuilderPromptYaml.get_prompt("care_agent.yaml")

care_agent = create_agent(
    model=MyModel.get_model(),
    system_prompt=prompt,
)


def _last_chat_days(user_id: int) -> int | None:
    """距离上次聊天的天数"""
    from app.common.mysql_db import mysql_db

    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT MAX(m.created_at) AS t FROM messages m "
            "JOIN conversations c ON m.session_id = c.session_id WHERE c.user_id=%s",
            (user_id,),
        )
        row = db["cursor"].fetchone()
    if not row or not row["t"]:
        return None
    return (datetime.now() - row["t"]).days


def _recent_emotions(user_id: int, n: int = 5) -> list[str]:
    from app.common.mysql_db import mysql_db

    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT emotion FROM emotion_records WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",
            (user_id, n),
        )
        rows = db["cursor"].fetchall()
    return [r["emotion"] for r in rows]


async def generate_care_message(user_id: int, kind: str = "care", memorial: dict | None = None) -> str:
    """生成主动关心/纪念日提醒消息"""
    working = WorkingMemory(user_id).query()
    profile = ProfileMemory(user_id).query()
    emotions = _recent_emotions(user_id)
    days = _last_chat_days(user_id)

    ctx = f"你对用户的整体了解：{(working or {}).get('summary') or '（暂无，你们可能刚认识）'}"
    if working and working.get("open_topics"):
        ctx += f"\n近期可以关心的话题：{'、'.join(working['open_topics'])}"
    if profile:
        known = [f"姓名{profile['name']}" if profile.get("name") else "",
                 f"职业{profile['occupation']}" if profile.get("occupation") else ""]
        ctx += "\n档案信息：" + "，".join(k for k in known if k) if any(known) else ""
        if profile.get("relationships"):
            ctx += f"，重要的人/事：{'、'.join(profile['relationships'])}"
    if emotions:
        ctx += f"\n用户近期情绪：{'、'.join(emotions)}"
    if days is not None:
        ctx += f"\n距上次聊天已经{days}天"
    else:
        ctx += "\n用户还没有和你聊过天"

    if kind == "memorial" and memorial:
        ctx += f"\n【重要】今天是用户的纪念日「{memorial['title']}」，请围绕这个纪念日送上真诚的祝福和关心"

    rs = await care_agent.ainvoke({"messages": [HumanMessage(content=ctx + "\n\n请生成这条主动消息。")]})
    return rs["messages"][-1].content
