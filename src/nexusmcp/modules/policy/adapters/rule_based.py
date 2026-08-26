"""S3-2 使用确定性特异性和 DENY Tie-Break 的 InMemory Policy Evaluator。"""

from collections.abc import Iterable

from nexusmcp.modules.policy.domain import (
    PolicyDecision,
    PolicyEffect,
    PolicyEvaluationInput,
    PolicySubjectType,
    ToolPolicy,
    ToolPolicyStatus,
)

_EFFECT_PRECEDENCE = {
    PolicyEffect.ALLOW: 1,
    PolicyEffect.REQUIRE_APPROVAL: 2,
    PolicyEffect.DENY: 3,
}


class RuleBasedPolicyEvaluator:
    def __init__(self, policies: Iterable[ToolPolicy]) -> None:
        self._policies = tuple(policies)

    async def evaluate(self, policy_input: PolicyEvaluationInput) -> PolicyDecision:
        candidates: list[tuple[int, ToolPolicy]] = []
        for policy in self._policies:
            specificity = _specificity(policy, policy_input)
            if specificity is not None:
                candidates.append((specificity, policy))
        if not candidates:
            return PolicyDecision.default_deny()

        max_specificity = max(specificity for specificity, _policy in candidates)
        specific = [policy for specificity, policy in candidates if specificity == max_specificity]
        max_priority = max(policy.priority for policy in specific)
        finalists = [policy for policy in specific if policy.priority == max_priority]
        selected = max(
            finalists,
            key=lambda policy: (_EFFECT_PRECEDENCE[policy.effect], policy.id),
        )
        return PolicyDecision(
            effect=selected.effect,
            policy_version=selected.version,
            reason_code=selected.reason_code,
        )


def _specificity(policy: ToolPolicy, policy_input: PolicyEvaluationInput) -> int | None:
    if policy.status is not ToolPolicyStatus.ACTIVE:
        return None
    if policy.tenant_id != policy_input.tenant_id or policy.action is not policy_input.action:
        return None
    if policy.tool_id is not None and policy.tool_id != policy_input.tool_id:
        return None
    principal = policy_input.principal
    if policy.subject_type is PolicySubjectType.PRINCIPAL:
        if policy.subject_id != principal.id:
            return None
        subject_score = 30
    elif policy.subject_type is PolicySubjectType.ROLE:
        if policy.subject_id not in principal.roles:
            return None
        subject_score = 20
    else:
        subject_score = 10
    tool_score = 1 if policy.tool_id is not None else 0
    return subject_score + tool_score
