from pydantic import BaseModel


class EmailTemplateCreate(BaseModel):
    name: str
    content: str


class EmailTemplateUpdate(BaseModel):
    name: str | None = None
    content: str | None = None


class EmailTemplateRead(BaseModel):
    id: int
    name: str
    content: str

    class Config:
        from_attributes = True
