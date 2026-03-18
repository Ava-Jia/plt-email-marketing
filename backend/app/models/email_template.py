"""邮件模版（管理员维护）：标题(唯一)+文字模版+图片物料列表。"""
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func

from app.database import Base

# status: pending=待发布, enabled=有效, disabled=已禁用
STATUS_PENDING = "pending"
STATUS_ENABLED = "enabled"
STATUS_DISABLED = "disabled"


class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True, index=True)
    # 作为“邮件标题/主题”，在业务侧要求唯一（DB 侧不强制 unique，避免 SQLite 迁移复杂度）
    name = Column(String(128), nullable=False)
    # 文字模版（可作为 AI prompt 的模板）
    content = Column(Text, nullable=False)
    # JSON 数组字符串，如 "[1,2,3]"，表示该模版默认包含的图片物料 id
    image_ids = Column(String(1000), nullable=True)
    status = Column(String(20), nullable=False, default=STATUS_PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
