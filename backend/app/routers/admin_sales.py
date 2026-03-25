"""管理员：销售用户 CRUD。邮箱即用户标识，用于登录及 CC。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import AdminUser
from app.models import User
from app.models.user import UserRole
from app.schemas.sales_user import SalesUserCreate, SalesUserUpdate, SalesUserRead
from app.services.auth_service import hash_password

router = APIRouter(prefix="/admin/sales", tags=["admin-sales"])


def _serialize(u: User) -> dict:
    email = (u.cc_email or u.login or "").strip()
    pwd = getattr(u, "password_plain", None)
    phone = getattr(u, "contact_phone", None) or ""
    return {
        "id": u.id,
        "email": email,
        "role": u.role,
        "password": pwd or "",
        "contact_phone": phone.strip() if isinstance(phone, str) else "",
    }


@router.get("", response_model=list[SalesUserRead])
def list_sales(
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    """列出所有销售用户。"""
    rows = db.query(User).filter(User.role == UserRole.sales.value).order_by(User.id).all()
    return [_serialize(r) for r in rows]


@router.post("", response_model=SalesUserRead, status_code=status.HTTP_201_CREATED)
def create_sales(
    data: SalesUserCreate,
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    """新建销售：用户/邮箱、密码。邮箱用于登录，同时是发件时被 CC 的邮箱。"""
    existing = db.query(User).filter(
        or_(User.login == data.email, User.cc_email == data.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该用户/邮箱已被使用")
    phone = (data.contact_phone or "").strip() or None
    user = User(
        name=data.email[:128],
        login=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.sales.value,
        cc_email=data.email,
        password_plain=data.password,
        contact_phone=phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.put("/{user_id}", response_model=SalesUserRead)
def update_sales(
    user_id: int,
    data: SalesUserUpdate,
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    """编辑销售：用户/邮箱、密码(可选)。"""
    row = db.query(User).filter(User.id == user_id, User.role == UserRole.sales.value).first()
    if not row:
        raise HTTPException(status_code=404, detail="销售用户不存在")
    if data.email is not None:
        other = db.query(User).filter(
            or_(User.login == data.email, User.cc_email == data.email),
            User.id != user_id,
        ).first()
        if other:
            raise HTTPException(status_code=400, detail="该用户/邮箱已被使用")
        row.login = data.email
        row.cc_email = data.email
        row.name = data.email[:128]
    if data.password is not None and data.password.strip():
        row.password_hash = hash_password(data.password)
        row.password_plain = data.password
    if "contact_phone" in data.model_fields_set:
        row.contact_phone = (data.contact_phone or "").strip() or None
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales(
    user_id: int,
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    """删除销售用户。"""
    row = db.query(User).filter(User.id == user_id, User.role == UserRole.sales.value).first()
    if not row:
        raise HTTPException(status_code=404, detail="销售用户不存在")
    db.delete(row)
    db.commit()
    return None
