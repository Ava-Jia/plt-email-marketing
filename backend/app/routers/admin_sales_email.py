"""管理员：销售-plt 邮箱 CRUD。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import AdminUser
from app.models import SalesPltEmail, SalesEmailAdminExcluded, User
from app.schemas.sales_plt_email import SalesPltEmailCreate, SalesPltEmailUpdate, SalesPltEmailRead

router = APIRouter(prefix="/admin/sales-email", tags=["admin-sales-email"])


@router.get("", response_model=list[SalesPltEmailRead])
def list_sales_emails(
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    return db.query(SalesPltEmail).order_by(SalesPltEmail.sales_id).all()


@router.post("", response_model=SalesPltEmailRead, status_code=status.HTTP_201_CREATED)
def create_sales_email(
    data: SalesPltEmailCreate,
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == data.sales_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="销售用户不存在")
    existing = db.query(SalesPltEmail).filter(SalesPltEmail.sales_id == data.sales_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="该销售已配置 plt 邮箱，请使用更新接口")
    row = SalesPltEmail(sales_id=data.sales_id, plt_email=data.plt_email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/users")
def list_users_for_admin(
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    """列出用户，供销售邮箱表使用。销售角色中，已被「清除」的不再返回。"""
    excluded_ids = {r.sales_id for r in db.query(SalesEmailAdminExcluded.sales_id).all()}
    users = db.query(User).order_by(User.id).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "login": u.login,
            "role": u.role,
            "cc_email": u.cc_email,
        }
        for u in users
        if not (u.role == "sales" and u.id in excluded_ids)
    ]


@router.put("/{item_id}", response_model=SalesPltEmailRead)
def update_sales_email(
    item_id: int,
    data: SalesPltEmailUpdate,
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    row = db.query(SalesPltEmail).filter(SalesPltEmail.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    row.plt_email = data.plt_email
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_email(
    item_id: int,
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    row = db.query(SalesPltEmail).filter(SalesPltEmail.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(row)
    db.commit()
    return None


@router.delete("/sales/{sales_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_sales_from_table(
    sales_id: int,
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    """清除：删除 plt 邮箱配置（若有），并将该销售从列表中移除（不再显示）。"""
    mapping = db.query(SalesPltEmail).filter(SalesPltEmail.sales_id == sales_id).first()
    if mapping:
        db.delete(mapping)
    existing = db.query(SalesEmailAdminExcluded).filter(SalesEmailAdminExcluded.sales_id == sales_id).first()
    if not existing:
        db.add(SalesEmailAdminExcluded(sales_id=sales_id))
    db.commit()
    return None
