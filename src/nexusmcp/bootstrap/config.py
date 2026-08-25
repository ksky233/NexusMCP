"""经过校验的应用配置。"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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
    local_tenant_id: str = "local"
    database_url: SecretStr | None = None
    database_echo: bool = False
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """为默认应用加载并缓存一份 Settings。"""

    return Settings()
