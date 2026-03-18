"""管理员：邮件话术模版 CRUD。"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models import EmailTemplate, SendSchedule, User
from app.services.app_logger import log_template_disabled, log_template_published
from app.models.email_template import STATUS_DISABLED, STATUS_ENABLED, STATUS_PENDING
from app.schemas.email_template import EmailTemplateCreate, EmailTemplateRead, EmailTemplateUpdate

router = APIRouter(prefix="/admin/templates", tags=["admin-templates"])


def _ensure_email_templates_columns(db: Session) -> None:
    """轻量迁移：保证 email_templates 必要列存在（兼容旧 sqlite db）。"""
    try:
        info = db.execute(sa.text("PRAGMA table_info(email_templates)")).fetchall()
        cols = {row[1] for row in info}
        if "image_ids" not in cols:
            db.execute(sa.text("ALTER TABLE email_templates ADD COLUMN image_ids VARCHAR(1000) NULL"))
            db.commit()
        if "enabled" not in cols:
            db.execute(sa.text("ALTER TABLE email_templates ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1"))
            db.commit()
        if "status" not in cols:
            db.execute(sa.text("ALTER TABLE email_templates ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'"))
            db.commit()
            if "enabled" in cols:
                db.execute(sa.text("UPDATE email_templates SET status='enabled' WHERE enabled=1 OR enabled IS NULL"))
                db.execute(sa.text("UPDATE email_templates SET status='disabled' WHERE enabled=0"))
            else:
                db.execute(sa.text("UPDATE email_templates SET status='enabled'"))
            db.commit()
    except Exception:
        pass


def _parse_ids(ids: list[int] | None) -> str | None:
    if not ids:
        return None
    try:
        norm = [int(x) for x in ids]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="image_ids 需为数字 id 列表")
    return json.dumps(norm)


def _serialize(row: EmailTemplate) -> dict:
    image_ids = None
    raw = getattr(row, "image_ids", None)
    if raw:
        try:
            image_ids = json.loads(raw)
        except Exception:
            image_ids = None
    s = getattr(row, "status", None) or STATUS_PENDING
    if s not in (STATUS_PENDING, STATUS_ENABLED, STATUS_DISABLED):
        s = STATUS_PENDING
    return {"id": row.id, "name": row.name, "content": row.content, "image_ids": image_ids, "status": s}


@router.get("", response_model=list[EmailTemplateRead])
def list_templates(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ensure_email_templates_columns(db)
    rows = db.query(EmailTemplate).order_by(EmailTemplate.created_at.desc(), EmailTemplate.id.desc()).all()
    return [_serialize(r) for r in rows]


@router.post("", response_model=EmailTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    data: EmailTemplateCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ensure_email_templates_columns(db)
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="模版名称不能为空")
    exists = db.query(EmailTemplate).filter(EmailTemplate.name == name).first()
    if exists:
        raise HTTPException(status_code=400, detail="模版名称已存在，请换一个名称")
    row = EmailTemplate(
        name=name,
        content=data.content,
        image_ids=_parse_ids(getattr(data, "image_ids", None)),
        status=STATUS_PENDING,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.put("/{item_id}", response_model=EmailTemplateRead)
def update_template(
    item_id: int,
    data: EmailTemplateUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ensure_email_templates_columns(db)
    row = db.query(EmailTemplate).filter(EmailTemplate.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="模版不存在")
    if data.name is not None:
        name = (data.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="模版名称不能为空")
        exists = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.name == name, EmailTemplate.id != item_id)
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="模版名称已存在，请换一个名称")
        row.name = name
    if data.content is not None:
        row.content = data.content
    if getattr(data, "image_ids", None) is not None:
        row.image_ids = _parse_ids(getattr(data, "image_ids", None))
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.patch("/{item_id}/publish")
def publish_template(
    item_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """发布模版：状态变为有效，销售端可见可用。"""
    _ensure_email_templates_columns(db)
    row = db.query(EmailTemplate).filter(EmailTemplate.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="模版不存在")
    row.status = STATUS_ENABLED
    db.commit()
    db.refresh(row)
    log_template_published(current_user.name or "", current_user.login or "", row.name or "", row.id)
    return _serialize(row)


@router.patch("/{item_id}/disable")
def disable_template(
    item_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """禁用模版：状态变为已禁用，计划任务将被取消。"""
    _ensure_email_templates_columns(db)
    row = db.query(EmailTemplate).filter(EmailTemplate.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="模版不存在")
    row.status = STATUS_DISABLED
    db.query(SendSchedule).filter(
        SendSchedule.template_id == item_id,
        SendSchedule.status.in_(["active", "sending"]),
    ).update({"status": "template_disabled"}, synchronize_session=False)
    db.commit()
    db.refresh(row)
    log_template_disabled(current_user.name or "", current_user.login or "", row.name or "", row.id)
    return _serialize(row)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    item_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(EmailTemplate).filter(EmailTemplate.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="模版不存在")
    db.delete(row)
    db.commit()
    return None
