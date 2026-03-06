"""FastAPI 应用入口。"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# 开发时在终端看到 preview / AI 等 INFO 日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from apscheduler.schedulers.background import BackgroundScheduler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import SessionLocal, engine
from app.models import Base, User  # noqa: F401
from app.routers import health, auth, me, admin_sales_email, customers, admin_images, admin_templates, preview, send, records
from app.routers.send import check_and_run_schedules
from app.services.auth_service import hash_password

_scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 先确保表存在（删除 db 后首次启动无表会报错）
    Base.metadata.create_all(bind=engine)
    # 若无任何用户则创建默认管理员（仅开发/首次部署方便）
    db = SessionLocal()
    try:
        if db.query(User).first() is None:
            admin = User(
                name="管理员",
                login="admin",
                password_hash=hash_password("Pltplt2026"),
                role="admin",
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()
    # 确保上传目录存在
    root = Path(__file__).resolve().parent.parent
    (root / settings.upload_dir / "images").mkdir(parents=True, exist_ok=True)
    # 简单迁移：为 email_records 表补充 status/sent_at 列（若不存在）
    with engine.begin() as conn:
        info = conn.exec_driver_sql("PRAGMA table_info(email_records)").fetchall()
        cols = {row[1] for row in info}
        if "status" not in cols:
            conn.exec_driver_sql("ALTER TABLE email_records ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'sent'")
        if "sent_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE email_records ADD COLUMN sent_at DATETIME NULL")
    _scheduler.add_job(check_and_run_schedules, "cron", minute="*", id="check_schedules", replace_existing=True)
    _scheduler.start()
    yield
    _scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

# CORS：允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 健康检查（便于部署与联调）
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(me.router, prefix="/api")
app.include_router(admin_sales_email.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(admin_images.router, prefix="/api")
app.include_router(admin_templates.router, prefix="/api")
app.include_router(preview.router, prefix="/api")
app.include_router(send.router, prefix="/api")
app.include_router(records.router, prefix="/api")

# 上传的图片通过 /uploads 提供访问
_upload_root = Path(__file__).resolve().parent.parent / settings.upload_dir
_upload_root.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_root)), name="uploads")


@app.get("/")
def root():
    return {"app": settings.app_name, "status": "ok"}
