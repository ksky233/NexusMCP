"""认证边界输出的可信 Internal Principal。"""

from dataclasses import dataclass
from enum import StrEnum


class PrincipalType(StrEnum):
    AGENT_SERVICE = "agent_service"
    ANONYMOUS = "anonymous"


@dataclass(frozen=True, slots=True)
class InternalPrincipal:
    """只包含认证后可信事实，不保存 Token 或原始 Claims。"""

    id: str
    tenant_id: str
    principal_type: PrincipalType
    authn_method: str

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("principal id must not be blank")
        if not self.tenant_id.strip():
            raise ValueError("principal tenant id must not be blank")
        if not self.authn_method.strip():
            raise ValueError("principal authentication method must not be blank")
