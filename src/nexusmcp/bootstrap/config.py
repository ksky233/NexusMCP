"""经过校验的应用配置。"""

import uuid
from functools import lru_cache
from ipaddress import ip_network
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
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
    telemetry_enabled: bool = False
    telemetry_exporter: Literal["none", "console", "otlp_http"] = "none"
    telemetry_otlp_endpoint: str | None = None
    telemetry_export_interval_ms: int = 60_000
    telemetry_export_timeout_seconds: float = 10.0
    upstream_egress_policy_enabled: bool = False
    upstream_allowed_hosts: list[str] = Field(default_factory=list)
    upstream_allowed_cidrs: list[str] = Field(default_factory=list)
    upstream_allowed_ports: list[int] = Field(default_factory=lambda: [80, 443])
    upstream_allow_local_demo: bool = False
    catalog_backend: Literal["memory", "postgresql"] = "memory"
    tool_discovery_mode: Literal["eager", "search_first"] = "eager"
    embedding_model: str = "Qwen/Qwen3-Embedding-8B"
    embedding_dimensions: int = 2048
    embedding_api_url: str = "https://api.siliconflow.cn/v1/embeddings"
    embedding_api_key: SecretStr | None = None
    embedding_timeout_seconds: float = 60.0
    embedding_batch_size: int = 16
    local_tenant_id: str = "local"
    mcp_identity_mode: Literal["static_service", "service_identity"] = "static_service"
    static_agent_principal_id: str = "local-agent-service"
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
    admin_identity_mode: Literal["local", "public_demo"] = "local"
    local_admin_principal_id: str = "local-admin"
    demo_admin_principal_id: str = "public-demo-admin"
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

    @field_validator("embedding_api_key", mode="before")
    @classmethod
    def normalize_empty_embedding_api_key(cls, value: object) -> object:
        # `.env.example` 有意保留空值；空 Key 表示未配置 Hybrid Provider，而不是一个可用 Secret。
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_runtime_mode(self) -> Self:
        if self.catalog_backend == "postgresql" and self.database_url is None:
            raise ValueError("database_url is required when catalog_backend is postgresql")
        if self.environment == "production" and self.catalog_backend != "postgresql":
            raise ValueError("production environment requires postgresql catalog_backend")
        if (
            self.environment == "production"
            and self.control_plane_enabled
            and self.admin_identity_mode != "public_demo"
        ):
            raise ValueError(
                "production Control Plane requires an explicit production Admin identity mode"
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
        if self.admin_identity_mode == "public_demo" and not self.control_plane_enabled:
            raise ValueError("public_demo Admin identity requires control_plane_enabled")
        if self.admin_identity_mode == "public_demo" and self.environment == "development":
            raise ValueError("public_demo Admin identity requires test or production environment")
        if self.admin_identity_mode == "local" and not self.local_admin_principal_id.strip():
            raise ValueError("local Admin identity requires local_admin_principal_id")
        if self.admin_identity_mode == "public_demo" and not self.demo_admin_principal_id.strip():
            raise ValueError("public_demo Admin identity requires demo_admin_principal_id")
        if (
            self.mcp_identity_mode == "static_service"
            and not self.static_agent_principal_id.strip()
        ):
            raise ValueError("static_service requires static_agent_principal_id")
        if self.database_readiness_timeout_seconds <= 0:
            raise ValueError("database_readiness_timeout_seconds must be positive")
        if self.telemetry_export_interval_ms <= 0:
            raise ValueError("telemetry_export_interval_ms must be positive")
        if self.telemetry_export_timeout_seconds <= 0:
            raise ValueError("telemetry_export_timeout_seconds must be positive")
        if self.telemetry_exporter == "otlp_http" and not self.telemetry_otlp_endpoint:
            raise ValueError("otlp_http telemetry exporter requires telemetry_otlp_endpoint")
        if self.telemetry_otlp_endpoint is not None and not self.telemetry_otlp_endpoint.startswith(
            ("https://", "http://")
        ):
            raise ValueError("telemetry_otlp_endpoint must use http or https")
        if any(not host.strip() for host in self.upstream_allowed_hosts):
            raise ValueError("upstream_allowed_hosts must not contain blank values")
        try:
            for cidr in self.upstream_allowed_cidrs:
                ip_network(cidr, strict=False)
        except ValueError:
            raise ValueError("upstream_allowed_cidrs contained an invalid network") from None
        if not self.upstream_allowed_ports or any(
            isinstance(port, bool) or not 1 <= port <= 65535 for port in self.upstream_allowed_ports
        ):
            raise ValueError("upstream_allowed_ports must contain valid ports")
        if not self.embedding_model.strip():
            raise ValueError("embedding_model must not be blank")
        if not 64 <= self.embedding_dimensions <= 8192:
            raise ValueError("embedding_dimensions must be between 64 and 8192")
        if not self.embedding_api_url.startswith(("https://", "http://")):
            raise ValueError("embedding_api_url must use http or https")
        if self.embedding_timeout_seconds <= 0:
            raise ValueError("embedding_timeout_seconds must be positive")
        if not 1 <= self.embedding_batch_size <= 64:
            raise ValueError("embedding_batch_size must be between 1 and 64")
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
        if self.environment == "production" and not self.upstream_egress_policy_enabled:
            raise ValueError("production requires upstream egress policy")
        if self.environment == "production" and self.upstream_allow_local_demo:
            raise ValueError("production cannot allow local demo upstreams")
        if (
            self.upstream_egress_policy_enabled
            and not self.upstream_allow_local_demo
            and not self.upstream_allowed_hosts
            and not self.upstream_allowed_cidrs
        ):
            raise ValueError("enabled upstream egress policy requires an allowlist")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """为默认应用加载并缓存一份 Settings。"""

    return Settings()
