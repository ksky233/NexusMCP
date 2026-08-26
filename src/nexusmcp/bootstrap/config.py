"""经过校验的应用配置。"""

import uuid
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """进程级配置；业务配置属于 Control Plane。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="NEXUSMCP_",
        extra="ignore",
    )

    app_name: str = "NexusMCP"
    service_name: str = "nexusmcp"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["console", "json"] = "console"
    catalog_backend: Literal["memory", "postgresql"] = "memory"
    local_tenant_id: str = "local"
    database_url: SecretStr | None = None
    database_echo: bool = False
    database_readiness_timeout_seconds: float = 1.0
    control_plane_enabled: bool = False
    tool_execution_enabled: bool = False
    tool_call_timeout_seconds: float = 5.0
    tool_retry_max_attempts: int = 3
    tool_retry_initial_backoff_seconds: float = 0.05
    approval_ttl_seconds: float = 600.0
    request_state_key: SecretStr | None = None
    local_admin_principal_id: str = "local-admin"
    openapi_fixture_root: Path = Path("examples/upstream_apis")
    transport_allowed_hosts: list[str] = Field(
        default_factory=lambda: [
            "127.0.0.1",
            "127.0.0.1:*",
            "localhost",
            "localhost:*",
            "testserver",
            "testserver:*",
        ]
    )
    transport_allowed_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_runtime_mode(self) -> Self:
        if self.catalog_backend == "postgresql" and self.database_url is None:
            raise ValueError("database_url is required when catalog_backend is postgresql")
        if self.environment == "production" and self.catalog_backend != "postgresql":
            raise ValueError("production environment requires postgresql catalog_backend")
        if self.environment == "production" and self.control_plane_enabled:
            raise ValueError(
                "local Control Plane must remain disabled in production before S3 authentication"
            )
        if self.control_plane_enabled and self.catalog_backend != "postgresql":
            raise ValueError("control_plane_enabled requires postgresql catalog_backend")
        if self.tool_execution_enabled and self.catalog_backend != "postgresql":
            raise ValueError("tool_execution_enabled requires postgresql catalog_backend")
        if self.control_plane_enabled:
            try:
                uuid.UUID(self.local_tenant_id)
            except ValueError:
                raise ValueError("control_plane_enabled requires UUID local_tenant_id") from None
        if self.database_readiness_timeout_seconds <= 0:
            raise ValueError("database_readiness_timeout_seconds must be positive")
        if self.tool_call_timeout_seconds <= 0:
            raise ValueError("tool_call_timeout_seconds must be positive")
        if not 1 <= self.tool_retry_max_attempts <= 10:
            raise ValueError("tool_retry_max_attempts must be between 1 and 10")
        if self.tool_retry_initial_backoff_seconds < 0:
            raise ValueError("tool_retry_initial_backoff_seconds must not be negative")
        if self.approval_ttl_seconds <= 0:
            raise ValueError("approval_ttl_seconds must be positive")
        if (
            self.request_state_key is not None
            and len(self.request_state_key.get_secret_value().encode("utf-8")) < 32
        ):
            raise ValueError("request_state_key must contain at least 32 bytes")
        if (
            self.environment == "production"
            and self.tool_execution_enabled
            and self.request_state_key is None
        ):
            raise ValueError("production tool execution requires request_state_key")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """为默认应用加载并缓存一份 Settings。"""

    return Settings()
