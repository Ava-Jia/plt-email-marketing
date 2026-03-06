"""管理员销售邮箱表中被「清除」的销售，不再显示在列表中。"""
from sqlalchemy import Column, Integer, ForeignKey

from app.database import Base


class SalesEmailAdminExcluded(Base):
    __tablename__ = "sales_email_admin_excluded"

    id = Column(Integer, primary_key=True, index=True)
    sales_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
