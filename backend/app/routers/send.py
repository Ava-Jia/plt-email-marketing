"""发送相关接口：测试发送 + 批量发送（SMTP + 限频）+ 循环发送计划。"""
import unicodedata
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import html
from pathlib import Path
import json
import mimetypes
import smtplib
import ssl
import threading
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, SessionLocal
from app.dependencies import CurrentUser
from app.models import CustomerList, EmailImage, EmailRecord, EmailTemplate, SendSchedule, User
from app.models.email_template import STATUS_ENABLED
from app.services.ai_content_service import get_content_for_preview
from app.services.app_logger import (
  log_batch_send_created,
  log_batch_send_start,
  log_batch_skip_no_record,
  log_email_failed,
  log_email_sent,
  log_schedule_cancelled,
  log_schedule_created,
  log_schedule_failed,
  log_schedule_run,
)

router = APIRouter(prefix="/send", tags=["send"])

SIGNATURE_TEXT = "此致\n湃乐多航运科技"


def _normalize_email_for_dedup(raw: str) -> str:
  """规范化邮箱用于去重：strip、小写、Unicode 标准化、移除不可见字符。
  避免同一邮箱因全角/零宽字符等差异被视为不同，导致重复发送。"""
  s = (raw or "").strip()
  if not s:
    return ""
  s = unicodedata.normalize("NFKC", s)  # 全角→半角、组合字符等
  s = "".join(c for c in s if unicodedata.category(c) != "Cf")  # 移除格式控制字符（零宽等）
  s = s.lower()
  return s
SIGNATURE_HTML = "<div style='margin:16px 0 0;font-size:14px;line-height:1.6;color:#111;'>此致<br/>湃乐多航运科技</div>"

def _ensure_email_templates_columns(db: Session) -> None:
  """轻量迁移：保证 email_templates 必要列存在（兼容旧 sqlite db）。"""
  try:
    info = db.execute(sa.text("PRAGMA table_info(email_templates)")).fetchall()
    cols = {row[1] for row in info}
    if "image_ids" not in cols:
      db.execute(sa.text("ALTER TABLE email_templates ADD COLUMN image_ids VARCHAR(1000) NULL"))
      db.commit()
    if "status" not in cols:
      db.execute(sa.text("ALTER TABLE email_templates ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'"))
      db.commit()
      if "enabled" in cols:
        db.execute(sa.text("UPDATE email_templates SET status='enabled' WHERE enabled=1 OR enabled IS NULL"))
        db.execute(sa.text("UPDATE email_templates SET status='disabled' WHERE enabled=0"))
        db.commit()
  except Exception:
    pass


def _get_cc_email_for_sales(db: Session, user: User) -> str | None:
  """获取销售发件时的 CC 邮箱：使用管理员配置的 cc_email。"""
  return (user.cc_email or "").strip() or None


def _resolve_template_and_image_names(
  db: Session,
  template_id: int | None,
  image_ids: list[int],
) -> tuple[str | None, list[str]]:
  """解析模版名称与图片名称，供日志可读。"""
  template_name = None
  if template_id:
    t = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
    if t:
      template_name = t.name
  image_names = []
  if image_ids:
    rows = db.query(EmailImage).filter(EmailImage.id.in_(image_ids)).all()
    id_to_name = {r.id: (r.name or Path(r.file_path).name) for r in rows}
    image_names = [id_to_name.get(i, str(i)) for i in image_ids]
  return template_name, image_names


class SendTestRequest(BaseModel):
  to_emails: list[str]  # 测试收件人邮箱，一个或多个，与客户表无关
  subject: str
  content: str
  image_ids: list[int] | None = None


class BatchSendRequest(BaseModel):
  template_id: int


class ScheduleCreateRequest(BaseModel):
  recurrence_type: str = "week"  # week | month
  day_of_week: int | None = None  # 0=周一 .. 6=周日，按周时必填
  day_of_month: int | None = None  # 1-31，按月时必填
  time: str  # "HH:MM"
  repeat_count: int = 1
  template_id: int  # 选择一套邮件方案（标题+文字模版+图片）


class ScheduleCancelRequest(BaseModel):
  pass  # PATCH body 可为空，或 {"status": "cancelled"}


_last_send_per_user: dict[int, datetime] = {}
_last_send_global: datetime | None = None
_global_pending_emails: int = 0
RATE_LIMIT_SECONDS = 30
# 严格全局串行：所有批次/计划发送共享同一把锁，避免多人同时触发时并发发送带来的风控风险
_global_send_lock = threading.Lock()
# 限速锁：确保 _send_smtp_email 的 30 秒间隔在多线程/多请求下严格执行
_rate_limit_lock = threading.Lock()


@router.get("/queue/status")
def get_queue_status(
  current_user: CurrentUser,
  db: Session = Depends(get_db),
):
  """查询当前队列状态（真实 DB 统计）。用于前端展示排队进度/预计等待时间。"""
  q = db.query(EmailRecord).filter(EmailRecord.status == "queued")
  queued_global = q.count()
  queued_mine = q.filter(EmailRecord.sales_id == current_user.id).count()
  # 严格全局串行 + 全局限速：预计分钟数 = 向上取整(queued_global * RATE_LIMIT_SECONDS / 60)
  eta_minutes = (queued_global * RATE_LIMIT_SECONDS + 59) // 60
  return {
    "queued_global": queued_global,
    "queued_mine": queued_mine,
    "rate_limit_seconds": RATE_LIMIT_SECONDS,
    "eta_minutes": eta_minutes,
  }


def _ensure_smtp_config() -> None:
  if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail="SMTP 配置不完整，请联系管理员在后端环境变量中填写 smtp_host / smtp_user / smtp_password。",
    )


def _build_attachments_from_image_ids(
  db: Session,
  image_ids: list[int] | None,
) -> list[tuple[str, str, bytes]]:
  """
  根据图片 id 列表构造附件：(filename, mimetype, data)。
  文件路径基于 settings.upload_dir 和 EmailImage.file_path。
  """
  if not image_ids:
    return []
  rows = (
    db.query(EmailImage)
    .filter(EmailImage.id.in_(image_ids))
    .all()
  )
  if not rows:
    return []

  backend_root = Path(__file__).resolve().parent.parent.parent  # backend/
  upload_root = backend_root / settings.upload_dir

  attachments: list[tuple[str, str, bytes]] = []
  for img in rows:
    try:
      full_path = upload_root / img.file_path  # 如 uploads/images/xxx.jpg
      data = full_path.read_bytes()
    except OSError:
      continue
    ctype, _ = mimetypes.guess_type(str(full_path))
    mimetype = ctype or "application/octet-stream"
    # EmailImage.name 来自原始文件名去后缀（admin_images.py），若直接用会导致附件无后缀难以打开
    raw_name = (img.name or "").strip()
    if raw_name:
      filename = raw_name if Path(raw_name).suffix else f"{raw_name}{full_path.suffix}"
      # 极端情况：full_path 没有后缀，则回退用真实文件名
      if not Path(filename).suffix:
        filename = full_path.name
    else:
      filename = full_path.name
    attachments.append((filename, mimetype, data))
  return attachments


def _build_inline_images_from_image_ids(
  db: Session,
  image_ids: list[int] | None,
) -> list[dict]:
  """
  根据图片 id 列表构造 inline 图片：
  [{"cid": "xxx", "maintype": "image", "subtype": "jpeg", "data": b"...", "filename": "a.jpg"}]
  """
  if not image_ids:
    return []
  rows = db.query(EmailImage).filter(EmailImage.id.in_(image_ids)).all()
  if not rows:
    return []
  backend_root = Path(__file__).resolve().parent.parent.parent  # backend/
  upload_root = backend_root / settings.upload_dir
  out: list[dict] = []
  for idx, img in enumerate(rows, start=1):
    try:
      full_path = upload_root / img.file_path
      data = full_path.read_bytes()
    except OSError:
      continue
    ctype, _ = mimetypes.guess_type(str(full_path))
    mimetype = ctype or "application/octet-stream"
    if "/" in mimetype:
      maintype, subtype = mimetype.split("/", 1)
    else:
      maintype, subtype = "application", "octet-stream"
    raw_name = (img.name or "").strip()
    filename = full_path.name
    if raw_name:
      filename = raw_name if Path(raw_name).suffix else f"{raw_name}{full_path.suffix}"
      if not Path(filename).suffix:
        filename = full_path.name
    cid = make_msgid()[1:-1]  # 去掉尖括号，HTML 中用 cid:xxx
    out.append({"cid": cid, "maintype": maintype, "subtype": subtype, "data": data, "filename": filename})
  return out


def _text_to_html(text: str) -> str:
  safe = html.escape(text or "").replace("\n", "<br/>")
  return f"<div style='font-size:14px;line-height:1.6;color:#111;'>{safe}</div>"


def _build_email_html(content_text: str, inline_images: list[dict]) -> str:
  imgs = ""
  for img in inline_images or []:
    cid = html.escape(img.get("cid") or "")
    if not cid:
      continue
    imgs += (
      "<div style='margin:12px 0 0;'>"
      f"<img src=\"cid:{cid}\" style='display:block;border:0;max-width:100%;height:auto;' width='600'/>"
      "</div>"
    )
  # 排版顺序：文字 -> 图片 -> 落款
  body = _text_to_html(content_text) + imgs + SIGNATURE_HTML
  return (
    "<!doctype html><html><body>"
    "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='font-family:Arial,Helvetica,sans-serif;'>"
    "<tr><td>"
    f"{body}"
    "</td></tr></table>"
    "</body></html>"
  )


def _send_smtp_email(
  to_email: str,
  subject: str,
  content: str,
  cc_email: str | None = None,
  inline_images: list[dict] | None = None,
) -> None:
  global _last_send_global

  # 全局限速：任意销售的任意邮件，30 秒 1 封（加锁避免并发绕过）
  with _rate_limit_lock:
    now = datetime.now(timezone.utc)
    if _last_send_global is not None:
      delta = (now - _last_send_global).total_seconds()
      if 0 <= delta < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - delta)
    _last_send_global = datetime.now(timezone.utc)

  msg = EmailMessage()
  msg["Subject"] = subject or "邮件预览测试"
  msg["From"] = settings.smtp_sender or settings.smtp_user
  msg["To"] = to_email
  # 显式设置 Date/Message-ID，降低部分邮箱客户端/网关的合并或去重概率
  msg["Date"] = formatdate(localtime=True)
  msg["Message-ID"] = make_msgid()
  if cc_email:
    msg["Cc"] = cc_email
  # 纯文本兜底 + HTML 正文（含 CID 内嵌图片）
  plain = (content or "").rstrip()
  if plain:
    plain = f"{plain}\n\n{SIGNATURE_TEXT}"
  else:
    plain = SIGNATURE_TEXT
  msg.set_content(plain, subtype="plain", charset="utf-8")
  html_body = _build_email_html(content or "", inline_images or [])
  msg.add_alternative(html_body, subtype="html", charset="utf-8")
  if inline_images:
    html_part = msg.get_payload()[-1]  # text/html part
    for img in inline_images:
      cid = img.get("cid")
      if not cid:
        continue
      html_part.add_related(
        img.get("data") or b"",
        maintype=img.get("maintype") or "application",
        subtype=img.get("subtype") or "octet-stream",
        cid=f"<{cid}>",
        filename=img.get("filename") or None,
      )

  recipients = [to_email]
  if cc_email and cc_email not in recipients:
    recipients.append(cc_email)

  try:
    if settings.smtp_port == 465:
      context = ssl.create_default_context()
      with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as server:
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg, from_addr=msg["From"], to_addrs=recipients)
    else:
      with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg, from_addr=msg["From"], to_addrs=recipients)
  except Exception as exc:  # pragma: no cover - 网络错误在运行时体现
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"发送失败：{exc}",
    ) from exc


@router.post("/test")
def send_test_email(
  payload: SendTestRequest,
  current_user: CurrentUser,
  db: Session = Depends(get_db),
):
  """发送测试邮件：收件人由请求体 to_emails 指定（与客户表无关），Cc 为当前销售的 cc 邮箱；限频：每位销售每 30 秒 1 封。"""
  emails = [(e or "").strip() for e in (payload.to_emails or []) if (e or "").strip()]
  if not emails:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="请填写至少一个测试收件人邮箱。",
    )
  if not payload.content.strip():
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="邮件内容不能为空。",
    )

  # 限频：仅在本请求开始时检查一次（本请求内多封会按全局限速依次发送）
  now = datetime.now(timezone.utc)
  last = _last_send_per_user.get(current_user.id)
  if last and (now - last) < timedelta(seconds=RATE_LIMIT_SECONDS):
    raise HTTPException(
      status_code=status.HTTP_429_TOO_MANY_REQUESTS,
      detail="发送太频繁，每 30 秒仅可发送 1 封邮件。",
    )

  _ensure_smtp_config()
  cc_email = _get_cc_email_for_sales(db, current_user)
  inline_images = _build_inline_images_from_image_ids(db, payload.image_ids or [])
  subject = payload.subject or "邮件预览测试"
  content = payload.content or ""
  sent_list: list[str] = []
  failed_list: list[tuple[str, str]] = []  # (email, detail)

  for to_email in emails:
    try:
      _send_smtp_email(to_email, subject, content, cc_email=cc_email, inline_images=inline_images)
      log_email_sent(
        current_user.name, current_user.login,
        to_email, cc_email, settings.smtp_sender or settings.smtp_user,
        content,
        [i.get("filename") for i in inline_images if i.get("filename")],
      )
      rec = EmailRecord(
        sales_id=current_user.id,
        to_email=to_email,
        from_email=settings.smtp_sender or settings.smtp_user,
        cc_email=cc_email,
        subject=subject,
        content=content,
        image_ids=json.dumps(payload.image_ids or []),
        status="sent",
        sent_at=datetime.now(timezone.utc),
      )
      db.add(rec)
      db.commit()
      sent_list.append(to_email)
    except HTTPException as e:
      detail = e.detail if isinstance(e.detail, str) else getattr(e.detail, "message", str(e.detail))
      log_email_failed(current_user.name, current_user.login, to_email, detail)
      failed_list.append((to_email, detail))
    except Exception as e:  # pragma: no cover
      detail = str(e)
      log_email_failed(current_user.name, current_user.login, to_email, detail)
      failed_list.append((to_email, detail))

  if sent_list:
    _last_send_per_user[current_user.id] = datetime.now(timezone.utc)

  return {
    "status": "ok",
    "sent": sent_list,
    "failed": [{"email": em, "detail": d} for em, d in failed_list],
    "cc": cc_email,
  }


def _run_batch_send(
  sales_id: int,
  template_id: int,
  image_ids: list[int] | None = None,
  schedule_ids: int | list[int] | None = None,
  custom_subject: str | None = None,
) -> None:
  """后台任务：对当前销售的全部客户依次发送邮件，每封间隔 30 秒（全局限速共享），可携带图片附件。
  custom_subject：若传入则作为邮件主题前缀（每封为 custom_subject - 客户名），否则用模版名。"""
  global _global_pending_emails
  db = SessionLocal()
  schedule_updated = False
  try:
    _ensure_email_templates_columns(db)
    # 严格全局串行：同一时间仅允许一个发送线程进入发送循环
    _global_send_lock.acquire()
    user = db.query(User).filter(User.id == sales_id).first()
    if not user:
      if schedule_ids is not None:
        _mark_schedule_failed(schedule_ids)
        log_schedule_failed(schedule_ids, "用户不存在")
      return

    # 读取模版内容与名称（用于主题）
    tpl = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
    if not tpl:
      if schedule_ids is not None:
        _mark_schedule_failed(schedule_ids)
        log_schedule_failed(schedule_ids, "模版不存在")
      return
    template_content = tpl.content or ""
    subject_prefix = (tpl.name or "").strip() or "营销邮件"

    try:
      _ensure_smtp_config()
    except Exception as e:
      if schedule_ids is not None:
        _mark_schedule_failed(schedule_ids)
        log_schedule_failed(schedule_ids, str(e))
      return
    # 若显式传入 image_ids（兼容旧计划），优先使用；否则取模版自带图片
    effective_image_ids = image_ids
    if not effective_image_ids:
      try:
        effective_image_ids = json.loads(getattr(tpl, "image_ids", None) or "[]")
      except Exception:
        effective_image_ids = []
    inline_images = _build_inline_images_from_image_ids(db, effective_image_ids or [])

    customers = (
      db.query(CustomerList)
      .filter(CustomerList.sales_id == sales_id)
      .order_by(CustomerList.id)
      .all()
    )
    # 按邮箱去重，同一邮箱只发一封（取第一条客户记录用于内容生成）
    # 使用 _normalize_email_for_dedup 防止全角/零宽字符等导致同一邮箱被视为不同
    seen_emails: set[str] = set()
    unique_customers: list[CustomerList] = []
    for cust in customers:
      raw = (cust.email or "").strip()
      if not raw:
        continue
      key = _normalize_email_for_dedup(raw)
      if not key or key in seen_emails:
        continue
      seen_emails.add(key)
      unique_customers.append(cust)

    cc_email = _get_cc_email_for_sales(db, user)
    from_email = settings.smtp_sender or settings.smtp_user

    queued_count = db.query(EmailRecord).filter(
      EmailRecord.sales_id == sales_id,
      EmailRecord.status == "queued",
    ).count()
    log_batch_send_start(user.login or "", len(unique_customers), queued_count)

    for cust in unique_customers:
      raw = (cust.email or "").strip()
      to_email = _normalize_email_for_dedup(raw) if raw else ""
      if not to_email:
        continue

      content = get_content_for_preview(
        customer_name=cust.customer_name,
        region=(cust.region or "").strip() or None,
        company_traits=(cust.company_traits or "").strip() or None,
        template=template_content or None,
      )
      subject = subject_prefix if subject_prefix else "营销邮件"

      # 找到一条排队中的记录
      rec = (
        db.query(EmailRecord)
        .filter(
          EmailRecord.sales_id == sales_id,
          EmailRecord.to_email == to_email,
          EmailRecord.status == "queued",
        )
        .order_by(EmailRecord.id)
        .first()
      )
      if rec is None:
        log_batch_skip_no_record(to_email, user.login or "")
        continue

      try:
        _send_smtp_email(to_email, subject, content, cc_email=cc_email, inline_images=inline_images)
        log_email_sent(
          user.name, user.login,
          to_email, cc_email, from_email,
          content or "",
          [i.get("filename") for i in inline_images if i.get("filename")],
        )
        rec.status = "sent"
        rec.subject = subject
        rec.content = content or ""
        rec.sent_at = datetime.now(timezone.utc)
      except HTTPException as e:
        # 单封失败：保留队列记录，并标记为已发送但附上错误信息，避免阻塞队列
        detail = e.detail if isinstance(e.detail, str) else getattr(e.detail, "message", str(e.detail))
        log_email_failed(user.name, user.login, to_email, detail)
        rec.status = "sent"
        rec.subject = subject or rec.subject
        rec.content = (content or "") + "\n\n[发送失败，详情见服务端日志]"
        rec.sent_at = datetime.now(timezone.utc)

      db.add(rec)
      db.commit()

      # 已发送一封，更新全局待发送数
      _global_pending_emails = max(0, _global_pending_emails - 1)

    # 仅当完整跑完发送循环后才更新计划状态（未抛异常、未提前 return）
    if schedule_ids is not None:
      _update_schedule_after_batch_done(schedule_ids)
      schedule_updated = True
  except Exception as e:
    if schedule_ids is not None and not schedule_updated:
      _mark_schedule_failed(schedule_ids)
      log_schedule_failed(schedule_ids, str(e))
  finally:
    try:
      if _global_send_lock.locked():
        _global_send_lock.release()
    except RuntimeError:
      pass
    db.close()


def _update_schedule_after_batch_done(schedule_ids: int | list[int]) -> None:
  """批量发送线程结束后调用：将计划的 current_count +1，status 置为 completed 或 active。支持多个计划（同一销售+模版合并执行时）。"""
  ids = [schedule_ids] if isinstance(schedule_ids, int) else schedule_ids
  db = SessionLocal()
  try:
    for sid in ids:
      row = db.query(SendSchedule).filter(SendSchedule.id == sid).first()
      if not row or row.status != "sending":
        continue
      new_count = (row.current_count or 0) + 1
      new_status = "completed" if new_count >= (row.repeat_count or 1) else "active"
      db.query(SendSchedule).filter(SendSchedule.id == sid).update(
        {"current_count": new_count, "status": new_status},
        synchronize_session=False,
      )
    db.commit()
  finally:
    db.close()


def _mark_schedule_failed(schedule_ids: int | list[int]) -> None:
  """发送过程发生异常时调用：将计划置为 failed，便于用户区分“未发就结束”的情况。"""
  ids = [schedule_ids] if isinstance(schedule_ids, int) else schedule_ids
  db = SessionLocal()
  try:
    for sid in ids:
      row = db.query(SendSchedule).filter(SendSchedule.id == sid).first()
      if not row or row.status != "sending":
        continue
      db.query(SendSchedule).filter(SendSchedule.id == sid).update(
        {"status": "failed"},
        synchronize_session=False,
      )
    db.commit()
  finally:
    db.close()


def _create_queued_records_for_sales(db: Session, sales_id: int, image_ids: list[int] | None = None) -> int:
  """为该销售的所有客户创建 status=queued 的 EmailRecord，返回创建条数。同一邮箱只创建一条，避免重复发送。"""
  user = db.query(User).filter(User.id == sales_id).first()
  if not user:
    return 0
  customers = (
    db.query(CustomerList)
    .filter(CustomerList.sales_id == sales_id)
    .order_by(CustomerList.id)
    .all()
  )
  from_email = settings.smtp_sender or settings.smtp_user
  cc_email = _get_cc_email_for_sales(db, user)
  seen_emails: set[str] = set()
  n = 0
  for cust in customers:
    raw = (cust.email or "").strip()
    if not raw:
      continue
    key = _normalize_email_for_dedup(raw)
    if not key or key in seen_emails:
      continue
    seen_emails.add(key)
    rec = EmailRecord(
      sales_id=sales_id,
      to_email=key,
      from_email=from_email,
      cc_email=cc_email,
      subject="",
      content="",
      image_ids=json.dumps(image_ids or []),
      status="queued",
    )
    db.add(rec)
    n += 1
  db.commit()
  return n


@router.post("/batch")
def start_batch_send(
  payload: BatchSendRequest,
  background_tasks: BackgroundTasks,
  current_user: CurrentUser,
  db: Session = Depends(get_db),
):
  """开始批量发送：对当前销售的客户表按顺序依次发送，每 30 秒 1 封（全销售共享限速队列）。"""
  global _global_pending_emails

  _ensure_email_templates_columns(db)
  tpl = db.query(EmailTemplate).filter(EmailTemplate.id == payload.template_id).first()
  if not tpl:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模版不存在")
  if getattr(tpl, "status", None) != STATUS_ENABLED:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该模版未发布或已禁用，销售端无法使用")
  tpl_image_ids = []
  try:
    tpl_image_ids = json.loads(getattr(tpl, "image_ids", None) or "[]") or []
  except Exception:
    tpl_image_ids = []
  n = _create_queued_records_for_sales(db, current_user.id, tpl_image_ids)
  _global_pending_emails += n
  tpl_name, img_names = _resolve_template_and_image_names(db, payload.template_id, tpl_image_ids)
  log_batch_send_created(current_user.name, current_user.login, tpl_name, img_names)

  background_tasks.add_task(
    _run_batch_send,
    current_user.id,
    payload.template_id,
    tpl_image_ids,
    None,
    None,
  )
  return {
    "status": "accepted",
    "detail": "已开始后台群发，将按队列顺序依次发送全部客户。你可以在「邮件记录」查看进度。",
  }


# ---------- 循环发送计划（方案 A：销售看自己，管理员看全部） ----------


def _parse_time(s: str) -> str:
  parts = (s or "").strip().split(":")
  if len(parts) != 2:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="time 格式为 HH:MM（北京时间）")
  try:
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
      raise ValueError("out of range")
    return f"{h:02d}:{m:02d}"
  except (ValueError, TypeError):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="time 需为有效 HH:MM")


@router.post("/schedule")
def create_schedule(
  payload: ScheduleCreateRequest,
  current_user: CurrentUser,
  db: Session = Depends(get_db),
):
  """创建循环发送计划。按周：day_of_week；按月：day_of_month。time 为北京时间 "HH:MM"。内容为所选模版+图片物料。"""
  recurrence = (payload.recurrence_type or "week").strip().lower()
  if recurrence not in ("week", "month"):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="recurrence_type 为 week 或 month")
  if payload.repeat_count < 1:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repeat_count 至少为 1")
  time_str = _parse_time(payload.time)

  day_of_week_val: int | None = None
  day_of_month_val: int | None = None
  if recurrence == "week":
    if payload.day_of_week is None:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="按周时需提供 day_of_week（0–6）")
    if payload.day_of_week < 0 or payload.day_of_week > 6:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="day_of_week 需为 0–6（周一至周日）")
    day_of_week_val = payload.day_of_week
  else:
    if payload.day_of_month is None:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="按月时需提供 day_of_month（1–31）")
    if payload.day_of_month < 1 or payload.day_of_month > 31:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="day_of_month 需为 1–31")
    day_of_month_val = payload.day_of_month
    day_of_week_val = 0  # 按月不用，存 0 以满足非空约束（若表未改可空）

  _ensure_email_templates_columns(db)
  tpl = db.query(EmailTemplate).filter(EmailTemplate.id == payload.template_id).first()
  if not tpl:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模版不存在")
  if getattr(tpl, "status", None) != STATUS_ENABLED:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该模版未发布或已禁用，无法创建计划")

  # 防重复：同一销售+模版+周期+时间 已存在 active 计划则拒绝
  q = db.query(SendSchedule).filter(
    SendSchedule.sales_id == current_user.id,
    SendSchedule.template_id == payload.template_id,
    SendSchedule.recurrence_type == recurrence,
    SendSchedule.time == time_str,
    SendSchedule.status == "active",
  )
  if recurrence == "week":
    q = q.filter(SendSchedule.day_of_week == day_of_week_val)
  else:
    q = q.filter(SendSchedule.day_of_month == day_of_month_val)
  if q.first():
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该模版在此时间已存在进行中的计划，请勿重复创建")

  row = SendSchedule(
    sales_id=current_user.id,
    recurrence_type=recurrence,
    day_of_week=day_of_week_val,
    day_of_month=day_of_month_val,
    time=time_str,
    repeat_count=payload.repeat_count,
    current_count=0,
    status="active",
    template_id=payload.template_id,
    image_ids=None,
    subject=None,
  )
  db.add(row)
  db.commit()
  db.refresh(row)
  tpl_image_ids = []
  try:
    tpl_image_ids = json.loads(getattr(tpl, "image_ids", None) or "[]") or []
  except Exception:
    tpl_image_ids = []
  tpl_name, img_names = _resolve_template_and_image_names(db, payload.template_id, tpl_image_ids)
  log_schedule_created(
    current_user.name, current_user.login,
    recurrence, day_of_week_val, day_of_month_val, time_str,
    tpl_name, img_names,
  )
  return {
    "id": row.id,
    "recurrence_type": row.recurrence_type,
    "day_of_week": row.day_of_week,
    "day_of_month": row.day_of_month,
    "time": row.time,
    "repeat_count": row.repeat_count,
    "current_count": 0,
    "status": row.status,
    "template_id": row.template_id,
    "image_ids": None,
    "subject": None,
    "created_at": row.created_at.isoformat() if row.created_at else None,
  }


@router.get("/schedules")
def list_schedules(
  current_user: CurrentUser,
  db: Session = Depends(get_db),
  status_filter: str | None = None,
):
  """计划列表：销售仅本人，管理员全部。可选 status_filter: active | completed | cancelled（含 template_disabled）。"""
  q = db.query(SendSchedule, User.name).join(User, SendSchedule.sales_id == User.id, isouter=True)
  if current_user.role != "admin":
    q = q.filter(SendSchedule.sales_id == current_user.id)
  if status_filter:
    if status_filter == "cancelled":
      q = q.filter(SendSchedule.status.in_(["cancelled", "template_disabled"]))
    else:
      q = q.filter(SendSchedule.status == status_filter)
  rows = q.order_by(SendSchedule.created_at.desc()).all()
  items = []
  for rec, sales_name in rows:
    image_ids = None
    if rec.image_ids:
      try:
        image_ids = json.loads(rec.image_ids)
      except Exception:
        pass
    template_name = None
    if rec.template_id:
      tpl = db.query(EmailTemplate).filter(EmailTemplate.id == rec.template_id).first()
      if tpl:
        template_name = tpl.name
    items.append({
      "id": rec.id,
      "sales_id": rec.sales_id,
      "sales_name": sales_name or "",
      "recurrence_type": getattr(rec, "recurrence_type", "week"),
      "day_of_week": rec.day_of_week,
      "day_of_month": rec.day_of_month,
      "time": rec.time,
      "repeat_count": rec.repeat_count,
      "current_count": rec.current_count,
      "status": rec.status,
      "template_id": rec.template_id,
      "template_name": template_name,
      "image_ids": image_ids,
      "subject": getattr(rec, "subject", None),
      "created_at": rec.created_at.isoformat() if rec.created_at else None,
    })
  return {"items": items}


@router.patch("/schedules/{schedule_id}")
def cancel_schedule(
  schedule_id: int,
  current_user: CurrentUser,
  db: Session = Depends(get_db),
):
  """取消计划：将 status 置为 cancelled。销售只能取消自己的，管理员可取消任意。"""
  row = db.query(SendSchedule).filter(SendSchedule.id == schedule_id).first()
  if not row:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="计划不存在")
  if current_user.role != "admin" and row.sales_id != current_user.id:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作该计划")
  if row.status not in ("active", "sending", "failed"):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能取消进行中、发送中或已失败的计划")
  owner = db.query(User).filter(User.id == row.sales_id).first()
  owner_name = owner.name if owner else ""
  rt = getattr(row, "recurrence_type", "week")
  if rt == "week":
    days = "周一,周二,周三,周四,周五,周六,周日"
    day_desc = days.split(",")[row.day_of_week] if row.day_of_week is not None else "?"
  else:
    day_desc = f"每月{row.day_of_month}日" if getattr(row, "day_of_month", None) else "?"
  schedule_desc = f"{day_desc} {row.time} (计划ID={row.id})"
  row.status = "cancelled"
  db.add(row)
  db.commit()
  log_schedule_cancelled(current_user.name, current_user.login, owner_name, schedule_desc)
  return {"ok": True, "detail": "已取消计划"}


# ---------- 定时任务：每分钟检查并执行到点的计划（由 main 启动的 APScheduler 调用） ----------

BEIJING_TZ = timezone(timedelta(hours=8))


def check_and_run_schedules() -> None:
  """按北京时间当前 星期或日期+时:分 匹配 active 计划，建队并异步执行发送。"""
  global _global_pending_emails
  db = SessionLocal()
  try:
    # 多进程互斥：仅有一个进程能执行本分钟的调度（uvicorn --workers N 时避免重复发送）
    now = datetime.now(BEIJING_TZ)
    minute_key = now.strftime("%Y-%m-%dT%H:%M")
    try:
      db.execute(sa.text("INSERT INTO cron_run_locks (minute_key) VALUES (:k)"), {"k": minute_key})
      db.commit()
    except Exception:
      db.rollback()
      return  # 其他进程已执行本分钟
    _ensure_email_templates_columns(db)
    weekday = now.weekday()  # 0=周一 .. 6=周日
    day_of_month = now.day  # 1-31
    time_str = now.strftime("%H:%M")
    all_active = (
      db.query(SendSchedule)
      .filter(
        SendSchedule.status == "active",
        SendSchedule.time == time_str,
        SendSchedule.current_count < SendSchedule.repeat_count,
      )
      .all()
    )
    rows = []
    for row in all_active:
      rt = getattr(row, "recurrence_type", "week")
      if rt == "week":
        if row.day_of_week == weekday:
          rows.append(row)
      else:
        dom = getattr(row, "day_of_month", None)
        if dom is None:
          continue
        last_day = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        effective = min(dom, last_day.day)
        if day_of_month == effective:
          rows.append(row)
    # 按 (sales_id, template_id) 合并：同一销售+模版在同一时刻只执行一次，避免重复发多封
    key_to_rows: dict[tuple[int, int | None], list] = {}
    for row in rows:
      db.refresh(row)
      if row.status != "active" or row.current_count >= row.repeat_count:
        continue
      if not row.template_id:
        continue
      tpl = db.query(EmailTemplate).filter(EmailTemplate.id == row.template_id).first()
      if tpl and getattr(tpl, "status", None) != STATUS_ENABLED:
        db.query(SendSchedule).filter(SendSchedule.id == row.id).update(
          {"status": "template_disabled"},
          synchronize_session=False,
        )
        db.commit()
        continue
      key = (row.sales_id, row.template_id)
      key_to_rows.setdefault(key, []).append(row)

    total_matched = sum(len(g) for g in key_to_rows.values())
    total_queued = 0
    for (sales_id, tid), group in key_to_rows.items():
      if not group:
        continue
      row0 = group[0]
      template_id = row0.template_id
      schedule_ids = [r.id for r in group]
      image_ids = None
      if row0.image_ids:
        try:
          image_ids = json.loads(row0.image_ids)
        except Exception:
          image_ids = None
      if not image_ids and template_id:
        tpl = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
        if tpl:
          try:
            image_ids = json.loads(getattr(tpl, "image_ids", None) or "[]") or []
          except Exception:
            image_ids = []
      n = _create_queued_records_for_sales(db, sales_id, image_ids or [])
      total_queued += n
      _global_pending_emails += n
      for r in group:
        db.query(SendSchedule).filter(SendSchedule.id == r.id).update(
          {"status": "sending"},
          synchronize_session=False,
        )
      db.commit()
      threading.Thread(
        target=_run_batch_send,
        args=(sales_id, template_id, image_ids or []),
        kwargs={
          "schedule_ids": schedule_ids,
          "custom_subject": None,
        },
        daemon=True,
      ).start()
    if key_to_rows:
      log_schedule_run(minute_key, total_matched, len(key_to_rows), total_queued)
  finally:
    db.close()

