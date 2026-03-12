import os
import sqlite3
import textwrap


def _db_path() -> str:
    # 默认读取 backend/ 目录下的 email_marketing.db
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "email_marketing.db")


def show(cur: sqlite3.Cursor, sql: str, limit: int = 20) -> None:
    print("\n" + "=" * 90)
    print("SQL:", sql)
    cur.execute(sql)
    cols = [d[0] for d in (cur.description or [])]
    rows = cur.fetchall()
    if cols:
        print("cols:", cols)
    for r in rows[:limit]:
        print(r)
    print(f"rows: {len(rows)} (showing up to {limit})")


def main() -> None:
    db_path = _db_path()
    print("DB:", db_path)
    if not os.path.exists(db_path):
        raise SystemExit(
            textwrap.dedent(
                f"""\
                找不到数据库文件：
                  {db_path}

                说明：
                - 默认 database_url 是 sqlite:///./email_marketing.db（相对 backend 目录）
                - 请确认你是在 backend 目录运行，或把数据库文件放在 backend 目录下
                """
            )
        )

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        print("\n--- tables ---")
        for (name,) in cur.execute("select name from sqlite_master where type='table' order by name"):
            print(name)

        show(cur, "select id, login, name, role, cc_email from users")
        show(cur, "select sales_id, count(*) as n from customer_list group by sales_id")
        show(
            cur,
            "select id, sales_id, recurrence_type, day_of_week, day_of_month, time, repeat_count, current_count, status, subject "
            "from send_schedules order by id desc limit 20",
        )
        show(
            cur,
            "select id, sales_id, to_email, cc_email, subject, status, created_at, sent_at "
            "from email_records order by id desc limit 50",
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()

