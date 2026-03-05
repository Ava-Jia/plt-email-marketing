"""销售与 pltplt 邮箱对应关系。"""
from sqlalchemy import Column, Integer, String, ForeignKey

from app.database import Base


class SalesPltEmail(Base):
    __tablename__ = "sales_plt_email"

    id = Column(Integer, primary_key=True, index=True)
    sales_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plt_email = Column(String(256), nullable=False)
