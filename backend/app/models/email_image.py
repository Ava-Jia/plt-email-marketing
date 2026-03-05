"""邮件图片物料（管理员上传）。"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.database import Base


class EmailImage(Base):
    __tablename__ = "email_images"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(256), nullable=False)
    file_path = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
