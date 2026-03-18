from pydantic import BaseModel


class EmailTemplateCreate(BaseModel):
    name: str
    content: str
    image_ids: list[int] | None = None


class EmailTemplateUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    image_ids: list[int] | None = None


class EmailTemplateRead(BaseModel):
    id: int
    name: str
    content: str
    image_ids: list[int] | None = None
    status: str = "pending"  # pending | enabled | disabled

    class Config:
        from_attributes = True
