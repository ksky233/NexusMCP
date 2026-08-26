"""Credential Binding 选择与 Secret 解析 Port。"""

from typing import Protocol

from nexusmcp.modules.credentials.domain import CredentialBinding, SecretReference, SecretValue
from nexusmcp.modules.identity.domain import InternalPrincipal


class CredentialBindingResolver(Protocol):
    async def resolve(
        self,
        tenant_id: str,
        principal: InternalPrincipal,
        tool_id: str,
        upstream_service_id: str,
    ) -> CredentialBinding | None: ...


class CredentialProvider(Protocol):
    async def resolve(self, reference: SecretReference) -> SecretValue: ...
