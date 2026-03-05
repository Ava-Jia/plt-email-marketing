"""管理员：图片物料上传、列表、删除。"""
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import require_admin
from app.models import EmailImage, User

router = APIRouter(prefix="/admin/images", tags=["admin-images"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _upload_dir() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    d = root / settings.upload_dir / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("")
def list_images(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """图片物料列表。"""
    rows = db.query(EmailImage).order_by(EmailImage.created_at.desc()).all()
    base = "/uploads/images"
    return [
        {"id": r.id, "name": r.name, "file_path": r.file_path, "url": f"{base}/{os.path.basename(r.file_path)}", "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]


@router.post("")
def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """上传图片物料。"""
    ext = Path((file.filename or "").lower()).suffix
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"仅支持图片格式：{', '.join(ALLOWED_EXTENSIONS)}")
    name = (file.filename or "image").rsplit(".", 1)[0][:200]
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")
    unique = uuid.uuid4().hex[:12]
    filename = f"{unique}{ext}"
    upload_d = _upload_dir()
    path = upload_d / filename
    path.write_bytes(content)
    relative_path = f"images/{filename}"
    row = EmailImage(name=name, file_path=relative_path)
    db.add(row)
    db.commit()
    db.refresh(row)
    base = "/uploads/images"
    return {"id": row.id, "name": row.name, "file_path": row.file_path, "url": f"{base}/{filename}", "created_at": row.created_at.isoformat() if row.created_at else None}


@router.delete("/{item_id}")
def delete_image(
    item_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除图片物料。"""
    row = db.query(EmailImage).filter(EmailImage.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    root = Path(__file__).resolve().parent.parent.parent
    path = root / settings.upload_dir / row.file_path
    if path.exists():
        path.unlink()
    db.delete(row)
    db.commit()
    return None
