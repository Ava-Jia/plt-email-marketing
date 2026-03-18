"""邮件预览：模版列表、所选话术、预览生成（前 3 条客户）、图片列表。"""
import json
import logging
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import CustomerList, EmailImage, EmailTemplate, User
from app.models.email_template import STATUS_ENABLED
from app.services.ai_content_service import get_content_for_preview

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/preview", tags=["preview"])

SIGNATURE_HTML = "<div style='margin:16px 0 0;font-size:14px;line-height:1.6;color:#111;'>此致<br/>湃乐多航运科技</div>"

class PreviewGenerateRequest(BaseModel):
    template_id: int | None = None


def _get_all_images(db: Session) -> list[dict]:
    rows = db.query(EmailImage).order_by(EmailImage.created_at.desc()).all()
    base = "/uploads/images"
    return [{"id": r.id, "name": r.name, "url": f"{base}/{os.path.basename(r.file_path)}"} for r in rows]


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
            else:
                db.execute(sa.text("UPDATE email_templates SET status='enabled'"))
            db.commit()
    except Exception:
        pass


def _image_urls_for_template(db: Session, tpl: EmailTemplate | None) -> list[dict]:
    """按 template.image_ids 顺序返回图片信息（id/name/url）。缺失的 id 自动跳过。"""
    if not tpl or not getattr(tpl, "image_ids", None):
        return []
    try:
        ids = json.loads(tpl.image_ids) or []
        ids = [int(x) for x in ids]
    except Exception:
        return []
    if not ids:
        return []
    rows = db.query(EmailImage).filter(EmailImage.id.in_(ids)).all()
    id_to_row = {r.id: r for r in rows}
    base = "/uploads/images"
    out = []
    for i in ids:
        r = id_to_row.get(i)
        if not r:
            continue
        out.append({"id": r.id, "name": r.name, "url": f"{base}/{os.path.basename(r.file_path)}"})
    return out


def _escape_html_text(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_preview_html(text: str, image_urls: list[str]) -> str:
    """浏览器预览用：图片直接用 URL（非 cid），布局尽量用 table + 行内样式。"""
    safe = _escape_html_text(text or "").replace("\n", "<br/>")
    imgs = ""
    for url in image_urls or []:
        u = _escape_html_text(url)
        imgs += (
            f"<div style='margin:12px 0 0;'>"
            f"<img src=\"{u}\" style='display:block;border:0;max-width:100%;height:auto;' width='600'/>"
            f"</div>"
        )
    return (
        "<!doctype html><html><body>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='font-family:Arial,Helvetica,sans-serif;'>"
        "<tr><td>"
        f"<div style='font-size:14px;line-height:1.6;color:#111;'>{safe}</div>"
        f"{imgs}"
        f"{SIGNATURE_HTML}"
        "</td></tr></table>"
        "</body></html>"
    )


@router.get("/templates")
def list_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """销售端：邮件模版下拉列表（仅返回 enabled=True 的模版）。"""
    _ensure_email_templates_columns(db)
    rows = db.query(EmailTemplate).filter(EmailTemplate.status == STATUS_ENABLED).order_by(EmailTemplate.id).all()
    items = []
    for r in rows:
        image_ids = None
        if getattr(r, "image_ids", None):
            try:
                image_ids = json.loads(r.image_ids)
            except Exception:
                image_ids = None
        items.append({"id": r.id, "name": r.name, "content": r.content, "image_ids": image_ids})
    return items


@router.post("")
def generate_preview(
    body: PreviewGenerateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按所选模版对客户表前 3 条各生成一封邮件内容（AI），返回 3 张预览卡片（含 html）+ 图片列表。"""
    template_content = ""
    tpl: EmailTemplate | None = None
    if body and body.template_id:
        tpl = db.query(EmailTemplate).filter(EmailTemplate.id == body.template_id).first()
        if tpl:
            template_content = tpl.content or ""
    tpl_images = _image_urls_for_template(db, tpl)
    tpl_image_urls = [x["url"] for x in tpl_images]
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
        html = build_preview_html(content, tpl_image_urls)
        contents.append({
            "customer_name": name,
            "region": region,
            "company_traits": traits,
            "email": c.email,
            "content": content,
            "html": html,
        })
    return {"contents": contents, "template_images": tpl_images, "images": _get_all_images(db)}


@router.get("/images")
def list_preview_images(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """预览用图片列表（当前可用物料）。"""
    return _get_all_images(db)

