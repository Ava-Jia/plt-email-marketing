"""客户列表（按销售维度，上传即全量覆盖）。"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func

from app.database import Base


class CustomerList(Base):
    __tablename__ = "customer_list"

    id = Column(Integer, primary_key=True, index=True)
    sales_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_name = Column(String(128), nullable=False)
    region = Column(String(128), nullable=True)
    company_traits = Column(String(512), nullable=True)
    email = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
