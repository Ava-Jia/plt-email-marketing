"""管理员：销售用户 CRUD schema。邮箱即用户标识，用于登录及 CC。"""
import re
from pydantic import BaseModel, field_validator

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class SalesUserCreate(BaseModel):
    """新建销售：用户/邮箱、密码。邮箱用于登录，同时也是发件时被 CC 的邮箱。"""
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("用户/邮箱不能为空")
        if not EMAIL_RE.match(v):
            raise ValueError("邮箱格式无效")
        return v[:256]

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not (v and v.strip()):
            raise ValueError("密码不能为空")
        p = v
        if len(p) < 8:
            raise ValueError("密码至少 8 位")
        if not re.search(r"[a-z]", p):
            raise ValueError("密码需包含小写字母")
        if not re.search(r"[A-Z]", p):
            raise ValueError("密码需包含大写字母")
        if not re.search(r"\d", p):
            raise ValueError("密码需包含数字")
        return v


class SalesUserUpdate(BaseModel):
    """编辑销售：用户/邮箱、密码(可选)。"""
    email: str | None = None
    password: str | None = None

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not EMAIL_RE.match(v):
            raise ValueError("邮箱格式无效")
        return v[:256]

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        p = v
        if len(p) < 8:
            raise ValueError("密码至少 8 位")
        if not re.search(r"[a-z]", p):
            raise ValueError("密码需包含小写字母")
        if not re.search(r"[A-Z]", p):
            raise ValueError("密码需包含大写字母")
        if not re.search(r"\d", p):
            raise ValueError("密码需包含数字")
        return v


class SalesUserRead(BaseModel):
    id: int
    email: str  # 用户/邮箱，用于登录及 CC
    role: str
    password: str = ""  # 明文密码，管理员可见

    class Config:
        from_attributes = True
