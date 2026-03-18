"""认证：登录。销售由管理员创建，可用 用户名或邮箱+密码 登录。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo
from app.services.auth_service import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """登录：支持 用户名或邮箱 + 密码。"""
    login_input = (data.login or "").strip()
    user = db.query(User).filter(
        or_(User.login == login_input, User.cc_email == login_input)
    ).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户/邮箱或密码错误",
        )
    token = create_access_token(sub=str(user.id), role=user.role)
    return LoginResponse(
        token=token,
        user=UserInfo(id=user.id, name=user.name, role=user.role),
    )
