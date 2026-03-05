"""ORM 模型。统一从本模块导出，便于 Alembic 发现。"""
from app.database import Base
from app.models.user import User, UserRole
from app.models.sales_plt_email import SalesPltEmail
from app.models.customer_list import CustomerList
from app.models.email_image import EmailImage
from app.models.email_template import EmailTemplate
from app.models.email_record import EmailRecord
from app.models.send_schedule import SendSchedule

__all__ = [
    "Base",
    "User",
    "UserRole",
    "SalesPltEmail",
    "CustomerList",
    "EmailImage",
    "EmailTemplate",
    "EmailRecord",
    "SendSchedule",
]
