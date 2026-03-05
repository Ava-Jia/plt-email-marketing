from pydantic import BaseModel


class SalesPltEmailCreate(BaseModel):
    sales_id: int
    plt_email: str


class SalesPltEmailUpdate(BaseModel):
    plt_email: str


class SalesPltEmailRead(BaseModel):
    id: int
    sales_id: int
    plt_email: str

    class Config:
        from_attributes = True
