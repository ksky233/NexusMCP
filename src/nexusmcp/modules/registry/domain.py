"""Registry 上下文的 Upstream Service 领域模型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any


class UpstreamServiceType(StrEnum):
    HTTP = "http"
    REMOTE_MCP = "remote_mcp"


class UpstreamStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class UpstreamService:
    """企业 HTTP 或 Remote MCP 服务的注册事实。"""

    id: str
    tenant_id: str
    namespace: str
    name: str
    description: str | None
    owner: str
    service_type: UpstreamServiceType
    transport_type: str
    endpoint: str
    protocol_min: str | None
    protocol_max: str | None
    auth_scheme: str | None
    config: Mapping[str, Any]
    status: UpstreamStatus

    def __post_init__(self) -> None:
        for field_name, value in (
            ("upstream service id", self.id),
            ("tenant id", self.tenant_id),
            ("upstream namespace", self.namespace),
            ("upstream name", self.name),
            ("upstream owner", self.owner),
            ("upstream transport type", self.transport_type),
            ("upstream endpoint", self.endpoint),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")

    def update(
        self,
        *,
        description: str | None,
        owner: str,
        endpoint: str,
        auth_scheme: str | None,
        config: Mapping[str, Any],
    ) -> UpstreamService:
        return replace(
            self,
            description=description,
            owner=owner,
            endpoint=endpoint,
            auth_scheme=auth_scheme,
            config=config,
        )

    def disable(self) -> UpstreamService:
        return (
            self
            if self.status is UpstreamStatus.DISABLED
            else replace(self, status=UpstreamStatus.DISABLED)
        )
