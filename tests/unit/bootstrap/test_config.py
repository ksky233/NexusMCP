"""运行模式与 Database Settings 组合约束测试。"""

import pytest
from pydantic import ValidationError

from nexusmcp.bootstrap.config import Settings


def test_postgresql_catalog_requires_database_url() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(environment="test", catalog_backend="postgresql", database_url=None)


def test_production_cannot_silently_use_empty_memory_catalog() -> None:
    with pytest.raises(ValidationError, match="production environment"):
        Settings(environment="production", catalog_backend="memory")


def test_database_readiness_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="must be positive"):
        Settings(environment="test", database_readiness_timeout_seconds=0)
