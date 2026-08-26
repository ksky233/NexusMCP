"""从进程环境变量按引用解析 Secret 的本地 Provider。"""

import os
import re
from collections.abc import Mapping

from nexusmcp.modules.credentials.domain import SecretReference, SecretValue
from nexusmcp.shared.errors import CredentialResolutionError

_ENVIRONMENT_PROVIDER = "environment"
_ENVIRONMENT_REFERENCE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class EnvironmentCredentialProvider:
    """仅接受受限环境变量名；错误消息不携带 Reference 或 Secret Value。"""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = environment if environment is not None else os.environ

    async def resolve(self, reference: SecretReference) -> SecretValue:
        if reference.provider != _ENVIRONMENT_PROVIDER:
            raise CredentialResolutionError("unsupported credential provider")
        if _ENVIRONMENT_REFERENCE.fullmatch(reference.reference) is None:
            raise CredentialResolutionError("invalid environment credential reference")
        value = self._environment.get(reference.reference)
        if not value:
            raise CredentialResolutionError("environment credential was unavailable")
        return SecretValue(value)
