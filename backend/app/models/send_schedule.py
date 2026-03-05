"""循环发送计划（按周或按月 + 时间触发，到点建队并发送；内容为所选模版+图片物料）。"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class SendSchedule(Base):
    __tablename__ = "send_schedules"

    id = Column(Integer, primary_key=True, index=True)
    sales_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recurrence_type = Column(String(10), nullable=False, default="week")  # week | month
    day_of_week = Column(Integer, nullable=True)  # 0=周一 .. 6=周日，按周时用
    day_of_month = Column(Integer, nullable=True)  # 1-31，按月时用
    time = Column(String(5), nullable=False)  # "HH:MM" 北京时间
    repeat_count = Column(Integer, nullable=False, default=1)
    current_count = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="active")  # active / completed / cancelled
    template_id = Column(Integer, ForeignKey("email_templates.id", ondelete="SET NULL"), nullable=True, index=True)
    image_ids = Column(String(1000), nullable=True)  # JSON 数组如 "[1,2,3]" 图片物料 id
    created_at = Column(DateTime(timezone=True), server_default=func.now())
