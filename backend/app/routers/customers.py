"""客户管理：上传（覆盖）、模板下载、摘要。"""
from io import BytesIO
from datetime import timezone, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import openpyxl

from app.database import get_db
from app.dependencies import get_current_user
from app.models import CustomerList, User
from app.services.customer_upload import parse_upload

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("/upload")
def upload_customers(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传客户表（Excel/CSV），按当前销售全量覆盖。"""
    content = file.file.read()
    records, errors = parse_upload(file.filename or "", content)
    if errors:
        raise HTTPException(status_code=400, detail={"message": "校验未通过", "errors": errors})
    if not records:
        raise HTTPException(status_code=400, detail="没有可导入的数据行")

    # 事务：先删后插
    db.query(CustomerList).filter(CustomerList.sales_id == current_user.id).delete()
    for r in records:
        row = CustomerList(
            sales_id=current_user.id,
            customer_name=r.get("customer_name", "").strip(),
            region=(r.get("region") or "").strip() or None,
            company_traits=(r.get("company_traits") or "").strip() or None,
            email=(r.get("email") or "").strip(),
        )
        db.add(row)
    db.commit()
    return {"message": "上传成功", "count": len(records)}


@router.get("/template")
def download_template(
    current_user: User = Depends(get_current_user),
):
    """下载客户表模板（xlsx）。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "客户列表"
    ws.append(["客户姓名", "区域", "公司特点", "客户邮箱"])
    ws.append(["张三", "深圳", "建设美国海外仓", "zhangsan@example.com"])
    ws.append(["李四", "宁波", "美国排名第一", "lisi@example.com"])
    ws.append(["王五", "上海", "准备启动上市计划", "wangwu@example.com"])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=customer_template.xlsx"},
    )


@router.get("")
def list_customers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 10,
):
    """当前销售的客户列表，分页（每页默认 10 条）。"""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 10
    q = db.query(CustomerList).filter(CustomerList.sales_id == current_user.id).order_by(CustomerList.id)
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": r.id,
                "customer_name": r.customer_name,
                "region": r.region or "",
                "company_traits": r.company_traits or "",
                "email": r.email,
            }
            for r in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/summary")
def get_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前销售的客户数量与最近更新时间。"""
    count = db.query(CustomerList).filter(CustomerList.sales_id == current_user.id).count()
    latest = (
        db.query(CustomerList.created_at)
        .filter(CustomerList.sales_id == current_user.id)
        .order_by(CustomerList.created_at.desc())
        .first()
    )
    # latest[0] 默认是 UTC 时间，这里统一转换为北京时间（UTC+8）再返回
    last_updated_iso = None
    if latest and latest[0]:
        dt = latest[0]
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        beijing = timezone(timedelta(hours=8))
        last_updated_iso = dt.astimezone(beijing).isoformat()
    return {
        "count": count,
        "last_updated": last_updated_iso,
    }


@router.get("/download-current")
def download_current_customers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """下载当前销售的全部客户列表（xlsx）。"""
    rows = (
        db.query(CustomerList)
        .filter(CustomerList.sales_id == current_user.id)
        .order_by(CustomerList.id)
        .all()
    )
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "当前客户"
    ws.append(["客户姓名", "区域", "公司特点", "客户邮箱"])
    for r in rows:
        ws.append([r.customer_name, r.region or "", r.company_traits or "", r.email])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=current_customers.xlsx"},
    )
