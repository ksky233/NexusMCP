"""协议无关的可信请求上下文。"""

from dataclasses import dataclass
from enum import StrEnum

ANONYMOUS_PRINCIPAL_ID = "anonymous"


class ProtocolEra(StrEnum):
    MODERN = "modern"
    LEGACY = "legacy"


@dataclass(frozen=True, slots=True, kw_only=True)
class ActorContext:
    request_id: str
    trace_id: str
    tenant_id: str
    principal_id: str
    authn_method: str
    principal_type: str = "agent_service"


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestContext(ActorContext):
    protocol_version: str
    protocol_era: ProtocolEra
    policy_snapshot: str | None = None
