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
from app.models import Base, User, SalesPltEmail  # noqa: F401
from app.routers import health, auth, me, admin_sales, customers, admin_images, admin_templates, preview, send, records
from app.routers.send import check_and_run_schedules
from app.services.auth_service import hash_password

_scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 先确保表存在（删除 db 后首次启动无表会报错）
    Base.metadata.create_all(bind=engine)
    # 迁移：将 SalesPltEmail 的 plt_email 同步到 User.cc_email（旧逻辑遗留）
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            for row in conn.execute(text("SELECT sales_id, plt_email FROM sales_plt_email")).fetchall():
                sid, email = row[0], (row[1] or "").strip()
                if email:
                    conn.execute(
                        text("UPDATE users SET cc_email = :e WHERE id = :id AND (cc_email IS NULL OR cc_email = '')"),
                        {"e": email, "id": sid},
                    )
    except Exception:
        pass
    # 迁移：为 users 表补充 password_plain 列（需在 query User 之前执行）
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            info_usr = conn.execute(text("PRAGMA table_info(users)")).fetchall()
            usr_cols = {row[1] for row in info_usr}
            if "password_plain" not in usr_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_plain VARCHAR(128) NULL"))
    except Exception:
        pass
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
        # 简单迁移：为 email_templates 表补充 image_ids 列（若不存在）
        info_tpl = conn.exec_driver_sql("PRAGMA table_info(email_templates)").fetchall()
        tpl_cols = {row[1] for row in info_tpl}
        if "image_ids" not in tpl_cols:
            conn.exec_driver_sql("ALTER TABLE email_templates ADD COLUMN image_ids VARCHAR(1000) NULL")
        if "status" not in tpl_cols:
            conn.exec_driver_sql("ALTER TABLE email_templates ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'")
            if "enabled" in tpl_cols:
                conn.exec_driver_sql("UPDATE email_templates SET status='enabled' WHERE enabled=1 OR enabled IS NULL")
                conn.exec_driver_sql("UPDATE email_templates SET status='disabled' WHERE enabled=0")
            else:
                conn.exec_driver_sql("UPDATE email_templates SET status='enabled'")
        # 迁移：将因模版禁用而取消的计划 status 从 cancelled 改为 template_disabled
        try:
            conn.exec_driver_sql(
                "UPDATE send_schedules SET status = 'template_disabled' "
                "WHERE status = 'cancelled' AND template_id IN (SELECT id FROM email_templates WHERE status = 'disabled')"
            )
        except Exception:
            pass
        # 定时任务互斥表：多进程时确保每分钟只有一个进程执行计划
        try:
            conn.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS cron_run_locks (minute_key TEXT PRIMARY KEY)"
            )
        except Exception:
            pass
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
app.include_router(admin_sales.router, prefix="/api")
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
