"""管理员：销售用户 CRUD schema。邮箱即用户标识，用于登录及 CC。"""
import re
from pydantic import BaseModel, field_validator

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

_MAX_PHONE_LEN = 64
_MAX_SIGN_NAME_LEN = 30


def _normalize_sign_name(v: str | None) -> str | None:
    if v is None:
        return None
    s = (v or "").strip()
    if not s:
        return None
    if len(s) > _MAX_SIGN_NAME_LEN:
        raise ValueError(f"用户姓名最多 {_MAX_SIGN_NAME_LEN} 个字符")
    return s


def _normalize_phone(v: str | None) -> str | None:
    if v is None:
        return None
    s = (v or "").strip()
    if not s:
        return None
    if len(s) > _MAX_PHONE_LEN:
        raise ValueError(f"联系方式最多 {_MAX_PHONE_LEN} 个字符")
    return s


class SalesUserCreate(BaseModel):
    """新建销售：用户姓名（落款）、邮箱、密码。邮箱用于登录，同时是发件时被 CC 的邮箱。"""
    email: str
    password: str
    sign_name: str | None = None
    contact_phone: str | None = None

    @field_validator("sign_name")
    @classmethod
    def sign_name_ok(cls, v: str | None) -> str | None:
        return _normalize_sign_name(v)

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

    @field_validator("contact_phone")
    @classmethod
    def phone_ok(cls, v: str | None) -> str | None:
        return _normalize_phone(v)


class SalesUserUpdate(BaseModel):
    """编辑销售：用户姓名、邮箱、密码(可选)、联系方式(可选，传空字符串可清空)。"""
    email: str | None = None
    password: str | None = None
    sign_name: str | None = None
    contact_phone: str | None = None

    @field_validator("sign_name")
    @classmethod
    def sign_name_ok(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _normalize_sign_name(v)

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

    @field_validator("contact_phone")
    @classmethod
    def phone_ok(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _normalize_phone(v)


class SalesUserRead(BaseModel):
    id: int
    email: str  # 邮箱，用于登录及 CC
    role: str
    password: str = ""  # 明文密码，管理员可见
    sign_name: str = ""  # 落款姓名
    contact_phone: str = ""

    class Config:
        from_attributes = True
