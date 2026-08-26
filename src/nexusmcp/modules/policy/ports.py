"""Policy Evaluation 出站 Port。"""

from typing import Protocol

from nexusmcp.modules.policy.domain import PolicyDecision, PolicyEvaluationInput


class PolicyEvaluator(Protocol):
    async def evaluate(self, policy_input: PolicyEvaluationInput) -> PolicyDecision: ...
