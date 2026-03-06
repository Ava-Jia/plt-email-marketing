"""发送相关接口：测试发送 + 批量发送（SMTP + 限频）+ 循环发送计划。"""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
import json
import mimetypes
import smtplib
import ssl
import threading
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, SessionLocal
from app.dependencies import CurrentUser
from app.models import CustomerList, EmailImage, EmailRecord, EmailTemplate, SalesPltEmail, SendSchedule, User
from app.services.ai_content_service import get_content_for_preview
from app.services.app_logger import (
  log_batch_send_created,
  log_email_failed,
  log_email_sent,
  log_schedule_cancelled,
  log_schedule_created,
)

router = APIRouter(prefix="/send", tags=["send"])


def _get_cc_email_for_sales(db: Session, user: User) -> str | None:
  """获取销售发件时的 CC 邮箱：优先使用管理员配置的 plt 邮箱，否则用注册时的 cc_email。"""
  m = db.query(SalesPltEmail).filter(SalesPltEmail.sales_id == user.id).first()
  if m and m.plt_email:
    return (m.plt_email or "").strip() or None
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
  to_email: str
  subject: str
  content: str
  image_ids: list[int] | None = None


class BatchSendRequest(BaseModel):
  template_id: int | None = None
  image_ids: list[int] | None = None


class ScheduleCreateRequest(BaseModel):
  recurrence_type: str = "week"  # week | month
  day_of_week: int | None = None  # 0=周一 .. 6=周日，按周时必填
  day_of_month: int | None = None  # 1-31，按月时必填
  time: str  # "HH:MM"
  repeat_count: int = 1
  template_id: int | None = None
  image_ids: list[int] | None = None  # 图片物料 id 列表，与预览所选一致


class ScheduleCancelRequest(BaseModel):
  pass  # PATCH body 可为空，或 {"status": "cancelled"}


_last_send_per_user: dict[int, datetime] = {}
_last_send_global: datetime | None = None
_global_pending_emails: int = 0
RATE_LIMIT_SECONDS = 60


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
    filename = img.name or full_path.name
    attachments.append((filename, mimetype, data))
  return attachments


def _send_smtp_email(
  to_email: str,
  subject: str,
  content: str,
  cc_email: str | None = None,
  attachments: list[tuple[str, str, bytes]] | None = None,
) -> None:
  global _last_send_global

  # 全局限速：任意销售的任意邮件，1 分钟 1 封
  now = datetime.now(timezone.utc)
  if _last_send_global is not None:
    delta = (now - _last_send_global).total_seconds()
    if 0 <= delta < RATE_LIMIT_SECONDS:
      time.sleep(RATE_LIMIT_SECONDS - delta)

  msg = EmailMessage()
  msg["Subject"] = subject or "邮件预览测试"
  msg["From"] = settings.smtp_sender or settings.smtp_user
  msg["To"] = to_email
  if cc_email:
    msg["Cc"] = cc_email
  msg.set_content(content or "", subtype="plain", charset="utf-8")

  if attachments:
    for filename, mimetype, data in attachments:
      maintype, subtype = (mimetype or "application/octet-stream").split("/", 1)
      msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

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
    _last_send_global = datetime.now(timezone.utc)
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
  """发送测试邮件：To 为客户邮箱，Cc 为当前销售的 cc 邮箱；限频：每位销售每分钟 1 封。"""
  to_email = (payload.to_email or "").strip()
  if not to_email:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="缺少客户邮箱地址。",
    )
  if not payload.content.strip():
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="邮件内容不能为空。",
    )

  # 限频：每位销售每分钟 1 封
  now = datetime.now(timezone.utc)
  last = _last_send_per_user.get(current_user.id)
  if last and (now - last) < timedelta(seconds=RATE_LIMIT_SECONDS):
    raise HTTPException(
      status_code=status.HTTP_429_TOO_MANY_REQUESTS,
      detail="发送太频繁，每分钟仅可发送 1 封邮件。",
    )

  _ensure_smtp_config()
  cc_email = _get_cc_email_for_sales(db, current_user)
  attachments = _build_attachments_from_image_ids(db, payload.image_ids or [])
  try:
    _send_smtp_email(to_email, payload.subject, payload.content, cc_email=cc_email, attachments=attachments)
  except HTTPException as e:
    detail = e.detail if isinstance(e.detail, str) else getattr(e.detail, "message", str(e.detail))
    log_email_failed(current_user.name, current_user.login, to_email, detail)
    raise
  log_email_sent(
    current_user.name, current_user.login,
    to_email, cc_email, settings.smtp_sender or settings.smtp_user,
    payload.subject or "邮件预览测试", payload.content or "",
    [a[0] for a in attachments],
  )

  # 记录发送日志
  rec = EmailRecord(
      sales_id=current_user.id,
      to_email=to_email,
      from_email=settings.smtp_sender or settings.smtp_user,
      cc_email=cc_email,
      subject=payload.subject or "",
      content=payload.content or "",
      image_ids=json.dumps(payload.image_ids or []),
      status="sent",
      sent_at=now,
  )
  db.add(rec)
  db.commit()

  _last_send_per_user[current_user.id] = now
  return {"status": "ok", "to": to_email, "cc": cc_email}


def _run_batch_send(sales_id: int, template_id: int | None, image_ids: list[int] | None = None) -> None:
  """后台任务：对当前销售的全部客户依次发送邮件，每封间隔 60 秒（全局限速共享），可携带图片附件。"""
  global _global_pending_emails
  db = SessionLocal()
  try:
    user = db.query(User).filter(User.id == sales_id).first()
    if not user:
      return

    # 读取模版内容与名称（用于主题）
    template_content = ""
    subject_prefix = "营销邮件"
    if template_id:
      tpl = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
      if tpl:
        template_content = tpl.content or ""
        if tpl.name:
          subject_prefix = tpl.name

    _ensure_smtp_config()
    attachments = _build_attachments_from_image_ids(db, image_ids or [])

    customers = (
      db.query(CustomerList)
      .filter(CustomerList.sales_id == sales_id)
      .order_by(CustomerList.id)
      .all()
    )
    cc_email = _get_cc_email_for_sales(db, user)
    from_email = settings.smtp_sender or settings.smtp_user

    for cust in customers:
      to_email = (cust.email or "").strip()
      if not to_email:
        continue

      content = get_content_for_preview(
        customer_name=cust.customer_name,
        region=(cust.region or "").strip() or None,
        company_traits=(cust.company_traits or "").strip() or None,
        template=template_content or None,
      )
      subject = f"{subject_prefix} - {cust.customer_name}" if subject_prefix else "营销邮件"

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
        # 若未预先创建队列记录，则跳过该行（理论上不应发生）
        continue

      try:
        _send_smtp_email(to_email, subject, content, cc_email=cc_email, attachments=attachments)
        log_email_sent(
          user.name, user.login,
          to_email, cc_email, from_email,
          subject, content or "",
          [a[0] for a in attachments],
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
  finally:
    db.close()


def _create_queued_records_for_sales(db: Session, sales_id: int, image_ids: list[int] | None = None) -> int:
  """为该销售的所有客户创建 status=queued 的 EmailRecord，返回创建条数。供即刻群发与定期计划共用。"""
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
  n = 0
  for cust in customers:
    to_email = (cust.email or "").strip()
    if not to_email:
      continue
    rec = EmailRecord(
      sales_id=sales_id,
      to_email=to_email,
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
  """开始批量发送：对当前销售的客户表按顺序依次发送，每分钟 1 封（全销售共享限速队列）。"""
  global _global_pending_emails

  n = _create_queued_records_for_sales(db, current_user.id, payload.image_ids or [])
  _global_pending_emails += n
  tpl_name, img_names = _resolve_template_and_image_names(db, payload.template_id, payload.image_ids or [])
  log_batch_send_created(current_user.name, current_user.login, tpl_name, img_names)

  q = db.query(EmailRecord).filter(EmailRecord.status == "queued")
  if current_user.role != "admin":
    q = q.filter(EmailRecord.sales_id == current_user.id)
  queued_count = q.count()

  background_tasks.add_task(_run_batch_send, current_user.id, payload.template_id, payload.image_ids or [])
  return {
    "status": "accepted",
    "detail": "已开始后台群发，将按队列顺序依次发送全部客户。你可以在「邮件记录」查看进度。",
    "queued": queued_count,
    "eta_minutes": queued_count,
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

  if payload.template_id is not None:
    tpl = db.query(EmailTemplate).filter(EmailTemplate.id == payload.template_id).first()
    if not tpl:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模版不存在")

  image_ids_json: str | None = None
  if payload.image_ids:
    try:
      ids = [int(x) for x in payload.image_ids]
    except (TypeError, ValueError):
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="image_ids 需为数字 id 列表",
      )
    image_ids_json = json.dumps(ids)

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
    image_ids=image_ids_json,
  )
  db.add(row)
  db.commit()
  db.refresh(row)
  tpl_name, img_names = _resolve_template_and_image_names(db, payload.template_id, payload.image_ids or [])
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
    "image_ids": payload.image_ids,
    "created_at": row.created_at.isoformat() if row.created_at else None,
  }


@router.get("/schedules")
def list_schedules(
  current_user: CurrentUser,
  db: Session = Depends(get_db),
  status_filter: str | None = None,
):
  """计划列表：销售仅本人，管理员全部。可选 status_filter: active | completed | cancelled。"""
  q = db.query(SendSchedule, User.name).join(User, SendSchedule.sales_id == User.id, isouter=True)
  if current_user.role != "admin":
    q = q.filter(SendSchedule.sales_id == current_user.id)
  if status_filter:
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
      "image_ids": image_ids,
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
  if row.status != "active":
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能取消进行中的计划")
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
    now = datetime.now(BEIJING_TZ)
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
    for row in rows:
      db.refresh(row)
      if row.status != "active" or row.current_count >= row.repeat_count:
        continue
      schedule_id, sales_id = row.id, row.sales_id
      template_id, repeat_count, current_count = row.template_id, row.repeat_count, row.current_count
      image_ids = None
      if row.image_ids:
        try:
          image_ids = json.loads(row.image_ids)
        except Exception:
          image_ids = None
      n = _create_queued_records_for_sales(db, sales_id, image_ids or [])
      _global_pending_emails += n
      new_count = current_count + 1
      new_status = "completed" if new_count >= repeat_count else "active"
      db.query(SendSchedule).filter(SendSchedule.id == schedule_id).update(
        {"current_count": new_count, "status": new_status},
        synchronize_session=False,
      )
      db.commit()
      threading.Thread(target=_run_batch_send, args=(sales_id, template_id, image_ids or []), daemon=True).start()
  finally:
    db.close()

