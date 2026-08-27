"""版本化 Policy Golden Matrix 回归。"""

import json
from pathlib import Path
from typing import Any

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
    ToolPolicyStatus,
)

CASES_PATH = Path(__file__).resolve().parents[2] / "evals" / "policy" / "policy_cases.json"


@pytest.mark.asyncio
async def test_policy_golden_matrix_is_complete_and_deterministic() -> None:
    payload: dict[str, Any] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    cases: list[dict[str, Any]] = payload["cases"]
    assert len(cases) == 10
    assert len({case["id"] for case in cases}) == len(cases)

    observed: dict[str, tuple[str, str, str]] = {}
    for case in cases:
        raw_principal = case["principal"]
        principal = InternalPrincipal(
            id=str(raw_principal["id"]),
            tenant_id=str(raw_principal["tenant_id"]),
            principal_type=(
                PrincipalType.AGENT
                if str(raw_principal["id"]).startswith("agent-")
                else PrincipalType.USER
            ),
            authn_method="golden_matrix",
            roles=frozenset(str(role) for role in raw_principal["roles"]),
        )
        policies = tuple(_policy(raw_policy) for raw_policy in case["policies"])
        decision = await RuleBasedPolicyEvaluator(policies).evaluate(
            PolicyEvaluationInput(
                tenant_id=principal.tenant_id,
                principal=principal,
                tool_id=str(case["tool_id"]),
                tool_version_id=f"{case['tool_id']}-v1",
                action=ToolAction.CALL,
                side_effect=ToolSideEffect(str(case["side_effect"])),
                arguments_digest="1" * 64,
            )
        )
        expected = case["expected"]
        actual = (decision.effect.value, decision.policy_version, decision.reason_code)
        assert actual == (
            str(expected["effect"]),
            str(expected["version"]),
            str(expected["reason_code"]),
        ), case["id"]
        observed[str(case["id"])] = actual

    assert set(observed) == {str(case["id"]) for case in cases}


def _policy(value: dict[str, Any]) -> ToolPolicy:
    return ToolPolicy(
        id=str(value["id"]),
        tenant_id=str(value["tenant_id"]),
        subject_type=PolicySubjectType(str(value["subject_type"])),
        subject_id=(str(value["subject_id"]) if value["subject_id"] is not None else None),
        tool_id=str(value["tool_id"]) if value["tool_id"] is not None else None,
        action=ToolAction.CALL,
        effect=PolicyEffect(str(value["effect"])),
        priority=int(value["priority"]),
        version=str(value["version"]),
        reason_code=str(value["reason_code"]),
        status=ToolPolicyStatus(str(value["status"])),
    )
