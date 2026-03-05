"""管理员：邮件话术模版 CRUD。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models import EmailTemplate, User
from app.schemas.email_template import EmailTemplateCreate, EmailTemplateRead, EmailTemplateUpdate

router = APIRouter(prefix="/admin/templates", tags=["admin-templates"])


@router.get("", response_model=list[EmailTemplateRead])
def list_templates(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(EmailTemplate).order_by(EmailTemplate.id).all()


@router.post("", response_model=EmailTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    data: EmailTemplateCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = EmailTemplate(name=data.name, content=data.content)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{item_id}", response_model=EmailTemplateRead)
def update_template(
    item_id: int,
    data: EmailTemplateUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(EmailTemplate).filter(EmailTemplate.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="模版不存在")
    if data.name is not None:
        row.name = data.name
    if data.content is not None:
        row.content = data.content
    db.commit()
    db.refresh(row)
    return row


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
