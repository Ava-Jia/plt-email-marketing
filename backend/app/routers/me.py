"""当前用户相关：CC 邮箱等。"""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import CurrentUser
from app.models import User

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/plt-email")
def get_my_plt_email(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """当前销售查询自己的 CC 邮箱（发件时被 CC）。"""
    user = db.query(User).filter(User.id == current_user.id).first()
    return {"plt_email": (user.cc_email or "").strip() or None}
