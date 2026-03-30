"""邮件发送记录：支持分页与按收件人/主题模糊筛选，以及按状态/To/From/Cc/发送日期筛选。"""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
import sqlalchemy as sa
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import CurrentUser
from app.models import EmailRecord, EmailImage, User
from app.services.app_logger import log_queued_cancelled

router = APIRouter(prefix="/records", tags=["records"])
BEIJING = timezone(timedelta(hours=8))


def _ensure_email_records_columns(db: Session) -> None:
    """轻量迁移：保证 email_records 必要列存在（兼容旧 sqlite db）。"""
    try:
        info = db.execute(sa.text("PRAGMA table_info(email_records)")).fetchall()
        cols = {row[1] for row in info}
        if "fixed_text" not in cols:
            db.execute(sa.text("ALTER TABLE email_records ADD COLUMN fixed_text TEXT NULL"))
            db.commit()
    except Exception:
        pass


def _to_beijing_iso(dt: datetime | None) -> str | None:
    """转为北京时间 ISO 字符串，避免前端再转时区导致晚 8 小时。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING).isoformat()


def _base_query(db: Session, current_user):
    """当前用户可见的记录基查询（销售仅本人，管理员全部）。"""
    q = db.query(EmailRecord)
    if current_user.role != "admin":
        q = q.filter(EmailRecord.sales_id == current_user.id)
    return q


def _build_record_content_summary(
    subject: str,
    content: str,
    fixed_text: str,
    image_names: list[str],
    sign_name: str | None,
    contact_phone: str | None,
) -> str:
    """邮件记录「内容摘要」：主题、AI、固定文本、附件、落款（与发信顺序一致）。"""
    footer_name = (sign_name or "").strip()[:30] or "湃乐多航运科技"
    phone = (contact_phone or "").strip()
    phone_line = phone if phone else "（未填）"
    att = "、".join(image_names) if image_names else "（无）"
    ft = (fixed_text or "").strip()
    closing = "新换单，湃乐多"
    return "\n".join(
        [
            f"主题：{subject or '（无主题）'}",
            "",
            "【AI 生成内容】",
            content or "（无）",
            "",
            "【固定文本】",
            ft or "（无）",
            "",
            "【附件】",
            att,
            "",
            "【落款】",
            footer_name,
            phone_line,
            closing,
        ]
    )


@router.get("/filters")
def get_record_filters(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    """返回各列的可选筛选值（去重），供前端下拉框使用。"""
    base = _base_query(db, current_user)

    statuses = ["queued", "sent", "failed", "expired"]
    to_emails = sorted(
        x[0] for x in base.with_entities(EmailRecord.to_email).distinct().all() if x[0]
    )
    from_emails = sorted(
        x[0] for x in base.with_entities(EmailRecord.from_email).distinct().all() if x[0]
    )
    cc_emails = sorted(
        x[0] for x in base.with_entities(EmailRecord.cc_email).distinct().all() if x[0]
    )

    sent_at_list = (
        base.with_entities(EmailRecord.sent_at)
        .filter(EmailRecord.sent_at.isnot(None))
        .all()
    )
    sent_dates = []
    for x in sent_at_list:
        if not x[0]:
            continue
        dt = x[0] if x[0].tzinfo else x[0].replace(tzinfo=timezone.utc)
        sent_dates.append(dt.astimezone(BEIJING).date().isoformat())
    sent_dates = sorted(set(sent_dates))

    return {
        "statuses": statuses,
        "to_emails": to_emails,
        "from_emails": from_emails,
        "cc_emails": cc_emails,
        "sent_dates": sent_dates,
    }


@router.get("")
def list_records(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 10,
    q: str | None = None,
    status: str | None = None,
    to_email: str | None = None,
    from_email: str | None = None,
    cc_email: str | None = None,
    sent_date: str | None = None,
    sent_date_from: str | None = None,
    sent_date_to: str | None = None,
):
    """当前用户（销售：仅本人；管理员：全部）的邮件记录列表，支持多列筛选。"""
    _ensure_email_records_columns(db)
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 10

    query = _base_query(db, current_user)

    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                EmailRecord.to_email.ilike(pattern),
                EmailRecord.subject.ilike(pattern),
                EmailRecord.content.ilike(pattern),
                EmailRecord.fixed_text.ilike(pattern),
            )
        )

    if status:
        if status == "expired":
            # 孤儿排队：queued 且创建超过 24 小时
            threshold = datetime.now(timezone.utc) - timedelta(hours=24)
            query = query.filter(
                EmailRecord.status == "queued",
                EmailRecord.sent_at.is_(None),
                EmailRecord.created_at < threshold,
            )
        else:
            query = query.filter(EmailRecord.status == status)
    if to_email:
        query = query.filter(EmailRecord.to_email == to_email)
    if from_email:
        query = query.filter(EmailRecord.from_email == from_email)
    if cc_email:
        query = query.filter(EmailRecord.cc_email == cc_email)
    # 兼容旧的 sent_date（单日），以及新的 sent_date_from/sent_date_to（区间）
    if sent_date:
        try:
            y, m, d = map(int, sent_date.split("-"))
            start_beijing = datetime(y, m, d, 0, 0, 0, tzinfo=BEIJING)
            end_beijing = start_beijing + timedelta(days=1)
            start_utc = start_beijing.astimezone(timezone.utc)
            end_utc = end_beijing.astimezone(timezone.utc)
            query = query.filter(
                EmailRecord.sent_at.isnot(None),
                EmailRecord.sent_at >= start_utc,
                EmailRecord.sent_at < end_utc,
            )
        except (ValueError, TypeError):
            pass
    else:
        start_utc = None
        end_utc = None
        if sent_date_from:
            try:
                y, m, d = map(int, sent_date_from.split("-"))
                start_beijing = datetime(y, m, d, 0, 0, 0, tzinfo=BEIJING)
                start_utc = start_beijing.astimezone(timezone.utc)
            except (ValueError, TypeError):
                start_utc = None
        if sent_date_to:
            try:
                y, m, d = map(int, sent_date_to.split("-"))
                # 结束日期按“当天 23:59:59.999”处理：区间为 [from, to+1天)
                end_beijing = datetime(y, m, d, 0, 0, 0, tzinfo=BEIJING) + timedelta(days=1)
                end_utc = end_beijing.astimezone(timezone.utc)
            except (ValueError, TypeError):
                end_utc = None
        if start_utc or end_utc:
            conds = [EmailRecord.sent_at.isnot(None)]  # sent_at 存在即视为已发送
            if start_utc:
                conds.append(EmailRecord.sent_at >= start_utc)
            if end_utc:
                conds.append(EmailRecord.sent_at < end_utc)
            query = query.filter(*conds)

    total = query.count()
    # 按发送时间从新到旧排序；无 sent_at 的按 created_at，SQLite 默认 DESC 时 NULL 在最后
    rows_recs = (
        query.order_by(EmailRecord.sent_at.desc(), EmailRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    user_ids = {r.sales_id for r in rows_recs if r.sales_id}
    users_map: dict[int, User] = {}
    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            users_map[u.id] = u

    # 预取本页所有记录涉及的图片名称，避免 N+1 查询
    image_ids_map: dict[int, list[int]] = {}
    image_id_set: set[int] = set()
    for rec in rows_recs:
        if rec.image_ids:
            try:
                ids = [int(x) for x in json.loads(rec.image_ids)]
            except Exception:
                ids = []
        else:
            ids = []
        image_ids_map[rec.id] = ids
        image_id_set.update(ids)

    image_name_by_id: dict[int, str] = {}
    if image_id_set:
        img_rows = db.query(EmailImage).filter(EmailImage.id.in_(image_id_set)).all()
        for img in img_rows:
            fn = Path(img.file_path).name if getattr(img, "file_path", None) else ""
            image_name_by_id[img.id] = fn or (img.name or str(img.id))

    now_utc = datetime.now(timezone.utc)
    orphan_threshold = now_utc - timedelta(hours=24)

    items = []
    for rec in rows_recs:
        # sent_at 优先：有发送时间即为已发送，修复 status 未正确更新的历史数据
        if rec.sent_at:
            display_status = "sent"
            sent_at_iso = _to_beijing_iso(rec.sent_at)
        else:
            sent_at_iso = None
            # 长期排队且无 sent_at：视为孤儿记录，显示为「排队超时」
            created_aware = rec.created_at
            if created_aware and created_aware.tzinfo is None:
                created_aware = created_aware.replace(tzinfo=timezone.utc)
            if rec.status == "queued" and created_aware and created_aware < orphan_threshold:
                display_status = "expired"
            else:
                display_status = rec.status or "sent"

        ids = image_ids_map.get(rec.id, [])
        image_names = [image_name_by_id.get(i, str(i)) for i in ids if i in image_name_by_id]
        owner = users_map.get(rec.sales_id) if rec.sales_id else None
        sales_name = (owner.name or "") if owner else ""
        sign_nm = getattr(owner, "sign_name", None) if owner else None
        contact_ph = getattr(owner, "contact_phone", None) if owner else None
        content_summary = _build_record_content_summary(
            rec.subject or "",
            rec.content or "",
            rec.fixed_text or "",
            image_names,
            sign_nm,
            contact_ph,
        )
        items.append(
            {
                "id": rec.id,
                "sales_id": rec.sales_id,
                "sales_name": sales_name,
                "to_email": rec.to_email,
                "from_email": rec.from_email,
                "cc_email": rec.cc_email,
                "subject": rec.subject or "",
                "content": rec.content,
                "fixed_text": rec.fixed_text or "",
                "image_names": image_names,
                "content_summary": content_summary,
                "status": display_status,
                "created_at": rec.created_at.isoformat() if isinstance(rec.created_at, datetime) else None,
                "sent_at": sent_at_iso,
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.delete("/{record_id}")
def cancel_queued_record(
    record_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    """取消排队中的邮件：仅允许取消 status=queued 且当前用户有权限的记录，取消后从队列移除且列表不再展示。"""
    rec = db.query(EmailRecord).filter(EmailRecord.id == record_id).first()
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    if current_user.role != "admin" and rec.sales_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作该记录")
    if rec.status != "queued":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能取消「排队中」的邮件")
    log_queued_cancelled(current_user.name, current_user.login, rec.to_email)
    db.delete(rec)
    db.commit()
    return {"ok": True, "detail": "已取消发送，该邮件已从队列中移除"}

