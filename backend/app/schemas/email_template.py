import json

from pydantic import BaseModel, Field


def deserialize_template_image_ids(raw: str | None) -> list[int]:
    """DB 中 JSON 列解析为 id 列表；无图、NULL、非法均为 []。"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []
        return [int(x) for x in parsed]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


class EmailTemplateCreate(BaseModel):
    name: str
    content: str
    fixed_text: str | None = None
    image_ids: list[int] | None = None


class EmailTemplateUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    fixed_text: str | None = None
    image_ids: list[int] | None = None


class EmailTemplateRead(BaseModel):
    id: int
    name: str
    content: str
    fixed_text: str = ""
    image_ids: list[int] = Field(default_factory=list)
    status: str = "pending"  # pending | enabled | disabled

    class Config:
        from_attributes = True
