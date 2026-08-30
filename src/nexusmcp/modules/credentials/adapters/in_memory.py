"""按确定性特异性规则选择 Credential Binding 的 InMemory Adapter。"""

from collections.abc import Iterable

from nexusmcp.modules.credentials.domain import (
    CredentialBinding,
    CredentialBindingStatus,
    CredentialSubjectType,
)
from nexusmcp.modules.identity.domain import InternalPrincipal
from nexusmcp.shared.errors import (
    CredentialBindingConflictError,
    TenantBoundaryViolationError,
)


class InMemoryCredentialBindingResolver:
    def __init__(self, bindings: Iterable[CredentialBinding]) -> None:
        self._bindings = tuple(bindings)

    async def resolve(
        self,
        tenant_id: str,
        principal: InternalPrincipal,
        tool_id: str,
        upstream_service_id: str,
    ) -> CredentialBinding | None:
        if principal.tenant_id != tenant_id:
            raise TenantBoundaryViolationError("principal crossed credential tenant boundary")

        candidates: list[tuple[int, CredentialBinding]] = []
        for binding in self._bindings:
            specificity = _specificity(
                binding,
                tenant_id=tenant_id,
                principal=principal,
                tool_id=tool_id,
                upstream_service_id=upstream_service_id,
            )
            if specificity is not None:
                candidates.append((specificity, binding))
        if not candidates:
            return None

        max_specificity = max(score for score, _binding in candidates)
        finalists = [binding for score, binding in candidates if score == max_specificity]
        # Credential 不允许靠插入顺序消除歧义；同级多个候选必须 Fail Closed。
        if len(finalists) != 1:
            raise CredentialBindingConflictError("credential binding selection was ambiguous")
        return finalists[0]


def _specificity(
    binding: CredentialBinding,
    *,
    tenant_id: str,
    principal: InternalPrincipal,
    tool_id: str,
    upstream_service_id: str,
) -> int | None:
    if binding.status is not CredentialBindingStatus.ACTIVE:
        return None
    if binding.tenant_id != tenant_id or binding.upstream_service_id != upstream_service_id:
        return None
    if binding.tool_id is not None and binding.tool_id != tool_id:
        return None
    if binding.subject_type is CredentialSubjectType.PRINCIPAL:
        if binding.subject_id != principal.id:
            return None
        subject_score = 30
    else:
        subject_score = 10
    tool_score = 1 if binding.tool_id is not None else 0
    return subject_score + tool_score
