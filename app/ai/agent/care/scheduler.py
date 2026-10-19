import asyncio
from datetime import date, datetime, timedelta

from app.common.mysql_db import mysql_db

"""
定时任务调度（纯asyncio实现，不引入额外依赖）：
1. 主动关心扫描：每轮检查，用户距上次收到主动消息超过24小时 -> 生成关心消息
2. 纪念日提醒：每天检查一次，当天/明天的纪念日 -> 生成提醒消息
3. 记忆清理：每天一次，清理遗忘殆尽的常规层(3)长期记忆（艾宾浩斯曲线）
应用lifespan中调用start_scheduler()启动。
"""

CHECK_INTERVAL = 30 * 60  # 检查间隔：30分钟
_last_memorial_date = None
_last_cleanup_date = None


def ensure_care_tables():
    """幂等建表（应用启动时调用）"""
    with mysql_db() as db:
        db["cursor"].execute("""
            CREATE TABLE IF NOT EXISTS proactive_messages (
                id         BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id    INT NOT NULL,
                kind       VARCHAR(20) DEFAULT 'care' COMMENT 'care=主动关心, memorial=纪念日提醒',
                content    TEXT NOT NULL,
                is_read    TINYINT DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                KEY idx_user (user_id)
            ) ENGINE=InnoDB COMMENT='AI主动消息表'
        """)
        db["cursor"].execute("""
            CREATE TABLE IF NOT EXISTS memorial_days (
                id            BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id       INT NOT NULL,
                title         VARCHAR(100) NOT NULL COMMENT '纪念日名称',
                date_str      VARCHAR(10) NOT NULL COMMENT 'MM-DD(每年重复) 或 YYYY-MM-DD(单次)',
                repeat_yearly TINYINT DEFAULT 1,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                KEY idx_user (user_id)
            ) ENGINE=InnoDB COMMENT='纪念日表'
        """)


# ---------- 数据库辅助 ----------
def _get_all_user_ids() -> list[int]:
    with mysql_db() as db:
        db["cursor"].execute("SELECT user_id FROM working_memory")
        return [r["user_id"] for r in db["cursor"].fetchall()]


def _last_care_time(user_id: int) -> datetime | None:
    with mysql_db() as db:
        db["cursor"].execute(
            "SELECT MAX(created_at) AS t FROM proactive_messages WHERE user_id=%s",
            (user_id,),
        )
        row = db["cursor"].fetchone()
    return row["t"] if row else None


def _save_proactive_message(user_id: int, kind: str, content: str):
    with mysql_db() as db:
        db["cursor"].execute(
            "INSERT INTO proactive_messages(user_id, kind, content) VALUES(%s,%s,%s)",
            (user_id, kind, content),
        )


def _get_memorial_days() -> list[dict]:
    with mysql_db() as db:
        db["cursor"].execute("SELECT id, user_id, title, date_str, repeat_yearly FROM memorial_days")
        return db["cursor"].fetchall()


def _memorial_matches(date_str: str, repeat_yearly: bool, targets: list[date]) -> bool:
    """纪念日是否命中目标日期（今天/明天）"""
    try:
        if repeat_yearly:
            m, d = date_str.split("-")
            return any(t.month == int(m) and t.day == int(d) for t in targets)
        y, m, d = date_str.split("-")
        return any(t.year == int(y) and t.month == int(m) and t.day == int(d) for t in targets)
    except Exception:
        return False


# ---------- 三个定时任务 ----------
async def care_scan():
    """主动关心：每用户24小时最多一条"""
    from app.ai.agent.care.care_agent import generate_care_message

    for user_id in _get_all_user_ids():
        last = _last_care_time(user_id)
        if last and datetime.now() - last < timedelta(hours=24):
            continue
        try:
            msg = await generate_care_message(user_id)
            _save_proactive_message(user_id, "care", msg)
            print(f"[主动关心] user_id={user_id}: {msg}")
        except Exception as e:
            print(f"主动关心生成失败 user_id={user_id}: {e}")
        await asyncio.sleep(3)  # 错开LLM调用


async def memorial_scan():
    """纪念日提醒：每天上午8点后检查一次，命中今天/明天的纪念日"""
    global _last_memorial_date
    today = date.today()
    if _last_memorial_date == today or datetime.now().hour < 8:
        return
    _last_memorial_date = today

    from app.ai.agent.care.care_agent import generate_care_message

    targets = [today, today + timedelta(days=1)]
    for md in _get_memorial_days():
        if not _memorial_matches(md["date_str"], bool(md["repeat_yearly"]), targets):
            continue
        try:
            msg = await generate_care_message(md["user_id"], kind="memorial", memorial=md)
            _save_proactive_message(md["user_id"], "memorial", msg)
            print(f"[纪念日提醒] user_id={md['user_id']}: {msg}")
        except Exception as e:
            print(f"纪念日提醒生成失败 user_id={md['user_id']}: {e}")
        await asyncio.sleep(3)


async def memory_cleanup():
    """记忆清理：每天一次，清理遗忘殆尽的常规层(3)长期记忆"""
    global _last_cleanup_date
    today = date.today()
    if _last_cleanup_date == today:
        return
    _last_cleanup_date = today

    from app.ai.memory.save.long_memory import LongMemory

    try:
        count = LongMemory().cleanup_expired()
        if count:
            print(f"[记忆清理] 遗忘清理{count}条长期记忆")
    except Exception as e:
        print(f"记忆清理异常: {e}")


async def _loop():
    await asyncio.sleep(60)  # 启动1分钟后开始第一轮
    while True:
        try:
            await memorial_scan()
            await care_scan()
            await memory_cleanup()
        except Exception as e:
            print(f"定时任务异常: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


def start_scheduler():
    """应用lifespan中调用，启动后台调度循环"""
    loop = asyncio.get_event_loop()
    loop.create_task(_loop())
    print("定时任务调度器已启动（主动关心/纪念日提醒/记忆清理）")
