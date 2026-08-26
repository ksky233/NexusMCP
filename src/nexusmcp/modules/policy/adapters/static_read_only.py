"""S3-1 只允许 Read-Only Tool 的最小 Policy Adapter。"""

from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.policy.domain import (
    PolicyDecision,
    PolicyEffect,
    PolicyEvaluationInput,
)


class StaticReadOnlyPolicyEvaluator:
    async def evaluate(self, policy_input: PolicyEvaluationInput) -> PolicyDecision:
        if policy_input.side_effect is ToolSideEffect.READ_ONLY:
            return PolicyDecision(
                effect=PolicyEffect.ALLOW,
                policy_version="static-read-only-v1",
                reason_code="read_only_allowed",
            )
        return PolicyDecision(
            effect=PolicyEffect.DENY,
            policy_version="static-read-only-v1",
            reason_code="write_not_enabled",
        )
