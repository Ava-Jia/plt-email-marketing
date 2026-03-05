"""邮件预览：模版列表、所选话术、预览生成（前 3 条客户）、图片列表。"""
import logging
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import CustomerList, EmailImage, EmailTemplate, User
from app.services.ai_content_service import get_content_for_preview

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/preview", tags=["preview"])


class PreviewGenerateRequest(BaseModel):
    template_id: int | None = None


@router.get("/templates")
def list_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """销售端：模版下拉列表（id, name, content）。"""
    rows = db.query(EmailTemplate).order_by(EmailTemplate.id).all()
    return [{"id": r.id, "name": r.name, "content": r.content} for r in rows]


@router.post("")
def generate_preview(
    body: PreviewGenerateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按所选模版对客户表前 3 条各生成一封邮件内容（AI），返回 3 张预览卡片 + 图片列表。"""
    template_content = ""
    if body and body.template_id:
        tpl = db.query(EmailTemplate).filter(EmailTemplate.id == body.template_id).first()
        if tpl:
            template_content = tpl.content or ""
    customers = (
        db.query(CustomerList)
        .filter(CustomerList.sales_id == current_user.id)
        .order_by(CustomerList.id)
        .limit(3)
        .all()
    )
    contents = []
    for c in customers:
        name = c.customer_name
        region = (c.region or "").strip()
        traits = (c.company_traits or "").strip()
        content = get_content_for_preview(
            customer_name=name,
            region=region or None,
            company_traits=traits or None,
            template=template_content or None,
        )
        contents.append({
            "customer_name": name,
            "region": region,
            "company_traits": traits,
            "email": c.email,
            "content": content,
        })
    rows = db.query(EmailImage).order_by(EmailImage.created_at.desc()).all()
    base = "/uploads/images"
    images = [{"id": r.id, "name": r.name, "url": f"{base}/{os.path.basename(r.file_path)}"} for r in rows]
    return {"contents": contents, "images": images}


@router.get("/images")
def list_preview_images(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """预览用图片列表（当前可用物料）。"""
    rows = db.query(EmailImage).order_by(EmailImage.created_at.desc()).all()
    base = "/uploads/images"
    return [
        {"id": r.id, "name": r.name, "url": f"{base}/{os.path.basename(r.file_path)}"}
        for r in rows
    ]

