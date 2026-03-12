"""应用日志：按日期写入 logs 目录，格式为 日期+时间+内容。"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading

from app.config import settings

# 日志目录：项目根目录 /logs（可由 settings.log_dir 覆盖）
_project_root = Path(__file__).resolve().parent.parent.parent.parent
_log_dir = _project_root / (settings.log_dir or "logs")
_lock = threading.Lock()

# 北京时间
BEIJING_TZ = timezone(timedelta(hours=8))


def _ensure_log_dir() -> Path:
    _log_dir.mkdir(parents=True, exist_ok=True)
    return _log_dir


def _log_file_path() -> Path:
    now = datetime.now(BEIJING_TZ)
    return _ensure_log_dir() / f"{now.strftime('%Y-%m-%d')}.log"


def write(content: str) -> None:
    """写入一行日志，格式：YYYY-MM-DD HH:MM:SS 内容"""
    now = datetime.now(BEIJING_TZ)
    line = f"{now.strftime('%Y-%m-%d %H:%M:%S')} {content}\n"
    with _lock:
        try:
            with open(_log_file_path(), "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass  # 写入失败时静默忽略


def log_register(login: str, name: str, email: str | None = None) -> None:
    """谁注册了账号（名称、邮箱；密码不记录，避免泄露）"""
    parts = [f"账号={login}", f"名称={name}"]
    if email:
        parts.append(f"邮箱={email}")
    write(f"[注册] {' '.join(parts)} 注册成功")


def log_batch_send_created(
    sales_name: str,
    sales_login: str,
    template_name: str | None,
    image_names: list[str],
    subject: str | None = None,
) -> None:
    """谁创建了群发任务（模版名、图片名为可读信息）"""
    tpl = f"模版={template_name}" if template_name else "无模版"
    imgs = f"图片=[{','.join(image_names)}]" if image_names else "无图片"
    subj = f"主题={subject}" if (subject or "").strip() else "无主题"
    write(f"[群发任务] {sales_name}（{sales_login}）创建群发任务，{subj}，{tpl}，{imgs}")


def log_schedule_created(
    sales_name: str,
    sales_login: str,
    recurrence_type: str,
    day_of_week: int | None,
    day_of_month: int | None,
    time_str: str,
    template_name: str | None,
    image_names: list[str],
    subject: str | None = None,
) -> None:
    """谁创建了循环任务、任务是什么（模版名、图片名为可读信息）"""
    if recurrence_type == "week":
        days = "周一,周二,周三,周四,周五,周六,周日"
        day_desc = days.split(",")[day_of_week] if day_of_week is not None else "?"
    else:
        day_desc = f"每月{day_of_month}日" if day_of_month else "?"
    tpl = f"模版={template_name}" if template_name else "无模版"
    imgs = f"图片=[{','.join(image_names)}]" if image_names else "无图片"
    subj = f"主题={subject}" if (subject or "").strip() else "无主题"
    write(f"[循环任务] {sales_name}（{sales_login}）创建循环任务：{day_desc} {time_str}，{subj}，{tpl}，{imgs}")


def log_email_sent(
    sales_name: str,
    sales_login: str,
    to_email: str,
    cc_email: str | None,
    from_email: str,
    subject: str,
    content_preview: str,
    image_attachments: list[str],
) -> None:
    """几点几分发了什么邮件（谁发的、给谁、CC给谁、From是谁、内容文本和图片附件）"""
    cc = cc_email or "无"
    content = (content_preview or "").replace("\n", " ")
    imgs = f"图片附件=[{','.join(image_attachments)}]" if image_attachments else "无图片附件"
    write(
        f"[发邮件] {sales_name}（{sales_login}）发邮件：To={to_email} CC={cc} From={from_email} "
        f"主题={subject} 内容={content} {imgs}"
    )


def log_email_failed(
    sales_name: str,
    sales_login: str,
    to_email: str,
    error_detail: str,
) -> None:
    """发送失败报错"""
    write(f"[发送失败] {sales_name}（{sales_login}）发往 To={to_email} 失败：{error_detail}")


def log_schedule_cancelled(
    operator_name: str,
    operator_login: str,
    schedule_owner_name: str,
    schedule_desc: str,
    subject: str | None = None,
) -> None:
    """循环任务取消：谁取消了谁的计划"""
    subj = f"主题={subject}" if (subject or "").strip() else "无主题"
    write(f"[循环任务取消] {operator_name}（{operator_login}）取消了 {schedule_owner_name} 的计划：{schedule_desc}，{subj}")


def log_queued_cancelled(
    operator_name: str,
    operator_login: str,
    to_email: str,
) -> None:
    """排队中任务取消：谁取消了发给谁的排队邮件"""
    write(f"[排队取消] {operator_name}（{operator_login}）取消了发往 To={to_email} 的排队邮件")
