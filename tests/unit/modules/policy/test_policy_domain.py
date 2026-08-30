"""Policy 三态决策与 Tenant 输入测试。"""

import pytest

from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.modules.policy.domain import (
    PolicyDecision,
    PolicyEffect,
    PolicyEvaluationInput,
    ToolAction,
)


def _principal(tenant_id: str = "tenant-a") -> InternalPrincipal:
    return InternalPrincipal(
        id="user-a",
        tenant_id=tenant_id,
        principal_type=PrincipalType.AGENT_SERVICE,
        authn_method="test",
    )


def test_default_policy_is_deny() -> None:
    decision = PolicyDecision.default_deny()

    assert decision.effect is PolicyEffect.DENY
    assert decision.reason_code == "default_deny"
    assert decision.requires_approval is False


def test_policy_decision_can_require_approval() -> None:
    decision = PolicyDecision(
        effect=PolicyEffect.REQUIRE_APPROVAL,
        policy_version="policy-v1",
        reason_code="write_requires_approval",
    )

    assert decision.requires_approval is True


def test_policy_input_rejects_cross_tenant_principal() -> None:
    with pytest.raises(ValueError, match="tenant"):
        PolicyEvaluationInput(
            tenant_id="tenant-a",
            principal=_principal("tenant-b"),
            tool_id="tool-1",
            tool_version_id="version-1",
            action=ToolAction.CALL,
            side_effect=ToolSideEffect.READ_ONLY,
            arguments_digest="1" * 64,
        )
