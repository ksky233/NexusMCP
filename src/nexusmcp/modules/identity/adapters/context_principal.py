"""S3-1 使用的可信 Context Principal Adapter；后续由 Authentication Adapter 替换。"""

from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.shared.request_context import ANONYMOUS_PRINCIPAL_ID, ActorContext


class ContextPrincipalResolver:
    async def resolve(self, context: ActorContext) -> InternalPrincipal:
        try:
            principal_type = PrincipalType(context.principal_type)
        except ValueError:
            principal_type = (
                PrincipalType.ANONYMOUS
                if context.principal_id == ANONYMOUS_PRINCIPAL_ID
                else PrincipalType.USER
            )
        return InternalPrincipal(
            id=context.principal_id,
            tenant_id=context.tenant_id,
            principal_type=principal_type,
            authn_method=context.authn_method,
            roles=context.roles,
            attributes=context.principal_attributes,
        )
