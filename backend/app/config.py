"""应用配置，从环境变量读取（pydantic-settings）。"""
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# 固定从 backend 目录读 .env，先显式加载到 os.environ，再交给 pydantic
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path, encoding="utf-8")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_env_path),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "邮件营销系统"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./email_marketing.db"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 3 # 72h

    # SMTP (pltplt)
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_sender: str = ""

    # AI API（.env 中填 AI_API_BASE_URL、AI_API_KEY）
    ai_api_base_url: str = ""
    ai_api_key: str = ""
    ai_api_model: str = "gpt-4o-mini"


    # 邮件内联图片：限长边；上传与规范化均为 PNG（optimize + compress_level=9）
    inline_image_max_side: int = 1400
    inline_jpeg_quality: int = 85  # 保留兼容 .env，当前内联链路已改用 PNG，未使用

    # 上传目录（相对项目根或绝对路径）
    upload_dir: str = "uploads"

    # 应用日志目录（按日期分文件，如 logs/2025-03-06.log）
    log_dir: str = "logs"

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


settings = Settings()
