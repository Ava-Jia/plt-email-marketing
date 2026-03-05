"""当前用户相关：plt 邮箱等。"""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import CurrentUser
from app.models import User, SalesPltEmail

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/plt-email")
def get_my_plt_email(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """当前销售查询自己是否已配置 plt 邮箱。"""
    row = db.query(SalesPltEmail).filter(SalesPltEmail.sales_id == current_user.id).first()
    return {"plt_email": row.plt_email if row else None}
