"""Policy 特异性、Priority、DENY Tie-Break 与 Default DENY 测试。"""

import pytest

from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.modules.policy.adapters.rule_based import RuleBasedPolicyEvaluator
from nexusmcp.modules.policy.domain import (
    PolicyEffect,
    PolicyEvaluationInput,
    PolicySubjectType,
    ToolAction,
    ToolPolicy,
)


def principal(principal_id: str = "sales-assistant-service") -> InternalPrincipal:
    return InternalPrincipal(
        id=principal_id,
        tenant_id="tenant-a",
        principal_type=PrincipalType.AGENT_SERVICE,
        authn_method="test",
    )


def policy(
    policy_id: str,
    *,
    subject_type: PolicySubjectType,
    subject_id: str | None,
    effect: PolicyEffect,
    tool_id: str | None = "tool-1",
    priority: int = 0,
) -> ToolPolicy:
    return ToolPolicy(
        id=policy_id,
        tenant_id="tenant-a",
        subject_type=subject_type,
        subject_id=subject_id,
        tool_id=tool_id,
        action=ToolAction.CALL,
        effect=effect,
        priority=priority,
        version="policy-v1",
        reason_code=f"{policy_id}_{effect.value}",
    )


def policy_input(principal_id: str = "sales-assistant-service") -> PolicyEvaluationInput:
    return PolicyEvaluationInput(
        tenant_id="tenant-a",
        principal=principal(principal_id),
        tool_id="tool-1",
        tool_version_id="version-1",
        action=ToolAction.CALL,
        side_effect=ToolSideEffect.READ_ONLY,
        arguments_digest="1" * 64,
    )


@pytest.mark.asyncio
async def test_no_matching_policy_defaults_to_deny() -> None:
    decision = await RuleBasedPolicyEvaluator(()).evaluate(policy_input())

    assert decision.effect is PolicyEffect.DENY
    assert decision.reason_code == "default_deny"


@pytest.mark.asyncio
async def test_exact_agent_service_policy_allows_matching_principal() -> None:
    evaluator = RuleBasedPolicyEvaluator(
        [
            policy(
                "reader",
                subject_type=PolicySubjectType.PRINCIPAL,
                subject_id="sales-assistant-service",
                effect=PolicyEffect.ALLOW,
            )
        ]
    )

    decision = await evaluator.evaluate(policy_input())

    assert decision.effect is PolicyEffect.ALLOW


@pytest.mark.asyncio
async def test_same_specificity_and_priority_prefers_deny() -> None:
    evaluator = RuleBasedPolicyEvaluator(
        [
            policy(
                "allow-reader",
                subject_type=PolicySubjectType.PRINCIPAL,
                subject_id="sales-assistant-service",
                effect=PolicyEffect.ALLOW,
            ),
            policy(
                "deny-reader",
                subject_type=PolicySubjectType.PRINCIPAL,
                subject_id="sales-assistant-service",
                effect=PolicyEffect.DENY,
            ),
        ]
    )

    decision = await evaluator.evaluate(policy_input())

    assert decision.effect is PolicyEffect.DENY


@pytest.mark.asyncio
async def test_exact_agent_service_policy_overrides_tenant_policy() -> None:
    evaluator = RuleBasedPolicyEvaluator(
        [
            policy(
                "deny-tenant",
                subject_type=PolicySubjectType.TENANT,
                subject_id=None,
                effect=PolicyEffect.DENY,
                priority=100,
            ),
            policy(
                "allow-agent-service",
                subject_type=PolicySubjectType.PRINCIPAL,
                subject_id="sales-assistant-service",
                effect=PolicyEffect.ALLOW,
            ),
        ]
    )

    decision = await evaluator.evaluate(policy_input())

    assert decision.effect is PolicyEffect.ALLOW
