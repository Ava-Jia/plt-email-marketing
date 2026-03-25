"""发送邮件记录（用于 /records 页面展示）。"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func

from app.database import Base


class EmailRecord(Base):
    __tablename__ = "email_records"

    id = Column(Integer, primary_key=True, index=True)
    sales_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    to_email = Column(String(256), nullable=False)
    from_email = Column(String(256), nullable=False)
    cc_email = Column(String(256), nullable=True)
    subject = Column(String(256), nullable=True)
    content = Column(String, nullable=False)
    fixed_text = Column(Text, nullable=True)  # 固定文本（不走 AI），插在 AI 正文与图片之间
    image_ids = Column(String, nullable=True)  # JSON，如 "[1,2,3]"，表示所附图片物料 id
    status = Column(String(32), nullable=False, default="sent")  # queued / sent
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

