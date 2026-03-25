"""Alembic 环境：绑定 Base.metadata，从 config 读取 database_url。"""
import logging
from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from alembic.script import ScriptDirectory

# 将 app 所在目录加入 path，以便 import app
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base
from app.config import settings

# 导入所有模型，使 Base.metadata 包含表定义
import app.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 使用 config.py 的 database_url，覆盖 alembic.ini 中的 url
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

_log = logging.getLogger("alembic.env")


def _applied_alembic_revision(connection) -> str | None:
    """当前库中记录的迁移版本；无表或无记录时返回 None。"""
    insp = sa.inspect(connection)
    if "alembic_version" not in insp.get_table_names():
        return None
    row = connection.execute(sa.text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
    return row if row else None


def _stamp_head_if_legacy_app_db(connection) -> bool:
    """若库已由应用先建表但从未写入 Alembic 版本，则仅写入 head，避免 upgrade 从 001 重复建表失败。"""
    insp = sa.inspect(connection)
    if "users" not in insp.get_table_names():
        return False
    if _applied_alembic_revision(connection) is not None:
        return False
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    if not head:
        return False
    # 不使用嵌套 begin()：部分驱动在 connect 后已有隐式事务
    connection.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
            """
        )
    )
    connection.execute(sa.text("DELETE FROM alembic_version"))
    connection.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": head})
    connection.commit()
    _log.warning(
        "检测到已有业务表但无 Alembic 版本记录（常见于先启动应用再执行 migrate）。"
        "已自动将版本标记为 head=%s，未重复执行 001 等历史迁移。全新空库仍会正常从 001 升级。",
        head,
    )
    return True


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL，不连接数据库。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if _stamp_head_if_legacy_app_db(connection):
            return
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
