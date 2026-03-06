import re
from pydantic import BaseModel, field_validator

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class LoginRequest(BaseModel):
    login: str
    password: str


class RegisterRequest(BaseModel):
    login: str
    password: str
    email: str

    @field_validator("login")
    @classmethod
    def login_not_empty(cls, v: str) -> str:
        if not (v and v.strip()):
            raise ValueError("账号不能为空")
        return v.strip()

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

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("邮箱不能为空")
        if not EMAIL_RE.match(v):
            raise ValueError("邮箱格式无效")
        return v


class LoginResponse(BaseModel):
    token: str
    user: "UserInfo"


class UserInfo(BaseModel):
    id: int
    name: str
    role: str

    class Config:
        from_attributes = True


LoginResponse.model_rebuild()
