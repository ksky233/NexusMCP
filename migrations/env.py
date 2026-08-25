"""Alembic Async Migration 环境。"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from nexusmcp.infrastructure.persistence.base import Base
from nexusmcp.infrastructure.persistence.models import ALL_MODELS

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入聚合器即可注册全部 Model；显式引用避免被静态检查视为无用导入。
_ = ALL_MODELS
target_metadata = Base.metadata


def get_database_url() -> str:
    """显式 Config URL 优先，普通 CLI 再读取环境变量。"""

    configured_url = config.get_main_option("sqlalchemy.url").strip()
    database_url = configured_url or os.getenv("NEXUSMCP_DATABASE_URL")
    if not database_url:
        raise RuntimeError("NEXUSMCP_DATABASE_URL is required for migrations")
    if not database_url.startswith("postgresql+asyncpg://"):
        raise RuntimeError("migration URL must use postgresql+asyncpg")
    return database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
