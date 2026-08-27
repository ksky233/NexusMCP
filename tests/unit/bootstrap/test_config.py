"""运行模式与 Database Settings 组合约束测试。"""

import pytest
from pydantic import SecretStr, ValidationError

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


def test_control_plane_requires_postgresql_and_uuid_tenant() -> None:
    with pytest.raises(ValidationError, match="requires postgresql"):
        Settings(
            environment="test",
            catalog_backend="memory",
            control_plane_enabled=True,
        )
    with pytest.raises(ValidationError, match="UUID local_tenant_id"):
        Settings(
            environment="test",
            catalog_backend="postgresql",
            database_url=SecretStr("postgresql+asyncpg://user:password@127.0.0.1/database"),
            control_plane_enabled=True,
            local_tenant_id="local",
        )


def test_local_control_plane_is_forbidden_in_production() -> None:
    with pytest.raises(ValidationError, match="disabled in production"):
        Settings(
            environment="production",
            catalog_backend="postgresql",
            database_url=SecretStr("postgresql+asyncpg://user:password@127.0.0.1/database"),
            local_tenant_id="00000000-0000-0000-0000-000000000001",
            control_plane_enabled=True,
        )


def test_tool_execution_requires_postgresql_and_positive_timeout() -> None:
    with pytest.raises(ValidationError, match="requires postgresql"):
        Settings(
            environment="test",
            catalog_backend="memory",
            tool_execution_enabled=True,
        )
    with pytest.raises(ValidationError, match="tool_call_timeout_seconds"):
        Settings(
            environment="test",
            tool_call_timeout_seconds=0,
        )
    with pytest.raises(ValidationError, match="tool_retry_max_attempts"):
        Settings(environment="test", tool_retry_max_attempts=0)
    with pytest.raises(ValidationError, match="backoff"):
        Settings(environment="test", tool_retry_initial_backoff_seconds=-1)


def test_request_state_key_and_approval_ttl_have_secure_bounds() -> None:
    with pytest.raises(ValidationError, match="approval_ttl_seconds"):
        Settings(environment="test", approval_ttl_seconds=0)
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(environment="test", request_state_key=SecretStr("short-key"))


def test_embedding_settings_validate_model_dimensions_and_url() -> None:
    with pytest.raises(ValidationError, match="embedding_model"):
        Settings(environment="test", embedding_model=" ")
    with pytest.raises(ValidationError, match="embedding_dimensions"):
        Settings(environment="test", embedding_dimensions=32)
    with pytest.raises(ValidationError, match="embedding_api_url"):
        Settings(environment="test", embedding_api_url="file:///tmp/embedding")
    with pytest.raises(ValidationError, match="embedding_timeout_seconds"):
        Settings(environment="test", embedding_timeout_seconds=0)
    with pytest.raises(ValidationError, match="embedding_batch_size"):
        Settings(environment="test", embedding_batch_size=65)


def test_empty_embedding_api_key_means_provider_is_not_configured() -> None:
    settings = Settings.model_validate({"environment": "test", "embedding_api_key": ""})

    assert settings.embedding_api_key is None


def test_telemetry_exporter_requires_safe_endpoint_and_positive_timing() -> None:
    with pytest.raises(ValidationError, match="telemetry_otlp_endpoint"):
        Settings(environment="test", telemetry_exporter="otlp_http")
    with pytest.raises(ValidationError, match="must use http or https"):
        Settings(environment="test", telemetry_otlp_endpoint="file:///tmp/otel")
    with pytest.raises(ValidationError, match="telemetry_export_interval_ms"):
        Settings(environment="test", telemetry_export_interval_ms=0)
    with pytest.raises(ValidationError, match="telemetry_export_timeout_seconds"):
        Settings(environment="test", telemetry_export_timeout_seconds=0)


def test_production_tool_execution_requires_shared_request_state_key() -> None:
    with pytest.raises(ValidationError, match="request_state_key"):
        Settings(
            environment="production",
            catalog_backend="postgresql",
            database_url=SecretStr("postgresql+asyncpg://user:password@127.0.0.1/database"),
            tool_execution_enabled=True,
        )
