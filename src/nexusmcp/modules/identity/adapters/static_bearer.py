"""S3-2 测试/开发使用、只保存 Token Digest 的 Bearer Authenticator。"""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.identity.domain import InternalPrincipal
from nexusmcp.shared.errors import AuthenticationError


@dataclass(frozen=True, slots=True)
class StaticBearerAgentServiceMapping:
    token: SecretValue
    principal: InternalPrincipal


class StaticBearerAgentServiceAuthenticator:
    """Opaque Bearer Token Digest 到 Agent Service Principal 的参考 Adapter。"""

    def __init__(
        self,
        identities: Iterable[StaticBearerAgentServiceMapping],
    ) -> None:
        self._principals_by_digest = {
            _token_digest(identity.token.reveal()): identity.principal for identity in identities
        }

    def authenticate(
        self,
        authorization_header: str | None,
        tenant_id: str,
    ) -> InternalPrincipal:
        if authorization_header is None:
            raise AuthenticationError("authorization header was missing")
        scheme, separator, token = authorization_header.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token:
            raise AuthenticationError("authorization header was not a valid bearer credential")
        principal = self._principals_by_digest.get(_token_digest(token))
        if principal is None or principal.tenant_id != tenant_id:
            raise AuthenticationError("bearer credential did not resolve to a trusted principal")
        return principal


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
