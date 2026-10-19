import os
from contextlib import contextmanager

import pymysql
from dotenv import load_dotenv

load_dotenv()


def get_conn():
    """获取MySQL连接（用完自动归还关闭）"""
    return pymysql.connect(
        host=os.getenv("MySQL_HOST"),
        port=int(os.getenv("MySQL_PORT")),
        user=os.getenv("MySQL_USER"),
        password=os.getenv("MySQL_PASSWORD"),
        database=os.getenv("MySQL_DATABASE"),
        charset=os.getenv("MySQL_CHARSET", "utf8mb4"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


@contextmanager
def mysql_db():
    """上下文管理器：自动提交/回滚/关闭

    with mysql_db() as db:
        db["cursor"].execute(sql, args)
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()
        yield {"conn": conn, "cursor": cursor}
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
