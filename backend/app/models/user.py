"""用户/销售与管理员。"""
from sqlalchemy import Column, Integer, String

from app.database import Base
import enum


class UserRole(str, enum.Enum):
    sales = "sales"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    login = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), nullable=False, default=UserRole.sales.value)
    cc_email = Column(String(256), nullable=True)  # 销售注册时填写的邮箱，作为发件时被 CC 的邮箱
    password_plain = Column(String(128), nullable=True)  # 明文密码，仅管理员可见，用于列表展示
    contact_phone = Column(String(64), nullable=True)  # 电话，邮件落款第二行
    sign_name = Column(String(30), nullable=True)  # 落款显示姓名，空则使用默认「湃乐多航运科技」
