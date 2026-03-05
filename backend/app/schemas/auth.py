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
    def password_not_empty(cls, v: str) -> str:
        if not (v and v.strip()):
            raise ValueError("密码不能为空")
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
