"""Tool Call Policy 输入与三态决策模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.identity.domain import InternalPrincipal


class ToolAction(StrEnum):
    CALL = "call"


class PolicyEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PolicySubjectType(StrEnum):
    PRINCIPAL = "principal"
    ROLE = "role"
    TENANT = "tenant"


class ToolPolicyStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    id: str
    tenant_id: str
    subject_type: PolicySubjectType
    subject_id: str | None
    tool_id: str | None
    action: ToolAction
    effect: PolicyEffect
    priority: int
    version: str
    reason_code: str
    status: ToolPolicyStatus = ToolPolicyStatus.ACTIVE

    def __post_init__(self) -> None:
        if self.subject_type is PolicySubjectType.TENANT and self.subject_id is not None:
            raise ValueError("tenant policy subject must not declare subject id")
        if self.subject_type is not PolicySubjectType.TENANT and not self.subject_id:
            raise ValueError("principal or role policy subject must declare subject id")
        if not self.version.strip() or not self.reason_code.strip():
            raise ValueError("policy version and reason code must not be blank")


@dataclass(frozen=True, slots=True)
class PolicyEvaluationInput:
    tenant_id: str
    principal: InternalPrincipal
    tool_id: str
    tool_version_id: str
    action: ToolAction
    side_effect: ToolSideEffect
    arguments_digest: str

    def __post_init__(self) -> None:
        if self.principal.tenant_id != self.tenant_id:
            raise ValueError("policy input principal crossed tenant boundary")


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    effect: PolicyEffect
    policy_version: str
    reason_code: str

    @classmethod
    def default_deny(cls) -> PolicyDecision:
        return cls(
            effect=PolicyEffect.DENY,
            policy_version="default",
            reason_code="default_deny",
        )

    @property
    def requires_approval(self) -> bool:
        return self.effect is PolicyEffect.REQUIRE_APPROVAL
