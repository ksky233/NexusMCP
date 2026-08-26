"""协议无关的可信请求上下文。"""

from dataclasses import dataclass
from enum import StrEnum

ANONYMOUS_PRINCIPAL_ID = "anonymous"


class ProtocolEra(StrEnum):
    MODERN = "modern"
    LEGACY = "legacy"


@dataclass(frozen=True, slots=True)
class ActorContext:
    request_id: str
    trace_id: str
    tenant_id: str
    principal_id: str
    authn_method: str


@dataclass(frozen=True, slots=True)
class RequestContext(ActorContext):
    protocol_version: str
    protocol_era: ProtocolEra
    agent_id: str | None = None
    run_id: str | None = None
    policy_snapshot: str | None = None
