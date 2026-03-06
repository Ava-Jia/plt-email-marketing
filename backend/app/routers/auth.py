"""认证：登录、注册。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models.user import UserRole
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, UserInfo
from app.services.auth_service import create_access_token, hash_password, verify_password
from app.services.app_logger import log_register

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.login == data.login).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录名或密码错误",
        )
    token = create_access_token(sub=str(user.id), role=user.role)
    return LoginResponse(
        token=token,
        user=UserInfo(id=user.id, name=user.name, role=user.role),
    )


@router.post("/register", response_model=LoginResponse)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """注册新销售：账号、密码、邮箱；邮箱将作为该销售发件时的被 CC 邮箱。"""
    existing = db.query(User).filter(User.login == data.login.strip()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该账号已被使用")
    name = data.login.strip()[:64]
    user = User(
        name=name,
        login=data.login.strip(),
        password_hash=hash_password(data.password),
        role=UserRole.sales.value,
        cc_email=data.email.strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_register(user.login, user.name, user.cc_email)
    token = create_access_token(sub=str(user.id), role=user.role)
    return LoginResponse(
        token=token,
        user=UserInfo(id=user.id, name=user.name, role=user.role),
    )
