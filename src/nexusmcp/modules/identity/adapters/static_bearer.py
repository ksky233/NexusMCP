"""S3-2 测试/开发使用、只保存 Token Digest 的 Bearer Authenticator。"""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.shared.errors import AuthenticationError
from nexusmcp.shared.request_context import ANONYMOUS_PRINCIPAL_ID


@dataclass(frozen=True, slots=True)
class StaticBearerIdentity:
    token: SecretValue
    principal: InternalPrincipal


class StaticBearerPrincipalAuthenticator:
    """仅用于确定性 S3 测试；生产阶段由 JWT/OIDC Adapter 替换。"""

    def __init__(
        self,
        identities: Iterable[StaticBearerIdentity],
        *,
        allow_anonymous: bool = True,
    ) -> None:
        self._principals_by_digest = {
            _token_digest(identity.token.reveal()): identity.principal for identity in identities
        }
        self._allow_anonymous = allow_anonymous

    def authenticate(
        self,
        authorization_header: str | None,
        tenant_id: str,
    ) -> InternalPrincipal:
        if authorization_header is None:
            if not self._allow_anonymous:
                raise AuthenticationError("authorization header was missing")
            return InternalPrincipal(
                id=ANONYMOUS_PRINCIPAL_ID,
                tenant_id=tenant_id,
                principal_type=PrincipalType.ANONYMOUS,
                authn_method="anonymous",
            )
        scheme, separator, token = authorization_header.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token:
            raise AuthenticationError("authorization header was not a valid bearer credential")
        principal = self._principals_by_digest.get(_token_digest(token))
        if principal is None or principal.tenant_id != tenant_id:
            raise AuthenticationError("bearer credential did not resolve to a trusted principal")
        return principal


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
