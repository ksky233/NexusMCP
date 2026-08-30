"""可信 ActorContext 到 InternalPrincipal 的解析 Port。"""

from typing import Protocol

from nexusmcp.modules.identity.domain import InternalPrincipal
from nexusmcp.shared.request_context import ActorContext


class PrincipalResolver(Protocol):
    async def resolve(self, context: ActorContext) -> InternalPrincipal: ...


class AgentServiceAuthenticator(Protocol):
    def authenticate(
        self,
        authorization_header: str | None,
        tenant_id: str,
    ) -> InternalPrincipal: ...
