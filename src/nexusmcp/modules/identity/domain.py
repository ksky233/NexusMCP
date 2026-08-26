"""认证边界输出的可信 Internal Principal。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class PrincipalType(StrEnum):
    USER = "user"
    SERVICE = "service"
    AGENT = "agent"
    ANONYMOUS = "anonymous"


type PrincipalAttribute = str | int | bool


@dataclass(frozen=True, slots=True)
class InternalPrincipal:
    """只包含认证后可信事实，不保存 Token 或原始 Claims。"""

    id: str
    tenant_id: str
    principal_type: PrincipalType
    authn_method: str
    roles: frozenset[str] = field(default_factory=frozenset)
    attributes: Mapping[str, PrincipalAttribute] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("principal id must not be blank")
        if not self.tenant_id.strip():
            raise ValueError("principal tenant id must not be blank")
        if not self.authn_method.strip():
            raise ValueError("principal authentication method must not be blank")
        if self.principal_type is PrincipalType.ANONYMOUS and self.roles:
            raise ValueError("anonymous principal must not carry trusted roles")
