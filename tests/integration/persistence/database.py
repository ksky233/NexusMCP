"""Integration Test 共用的测试数据库安全边界。"""

import os

import pytest
from alembic.config import Config
from sqlalchemy.engine import make_url


def require_test_database_url() -> str:
    """只允许测试操作显式命名的隔离数据库。"""

    database_url = os.getenv("NEXUSMCP_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("NEXUSMCP_TEST_DATABASE_URL is not configured")

    parsed = make_url(database_url)
    database_name = parsed.database or ""
    if "test" not in database_name.lower():
        raise RuntimeError("integration database name must include 'test'")
    if parsed.drivername != "postgresql+asyncpg":
        raise RuntimeError("integration database must use postgresql+asyncpg")
    return database_url


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config
