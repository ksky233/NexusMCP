"""Secret Reference、Credential Binding 与临时 Secret Value。"""

from dataclasses import dataclass
from enum import StrEnum


class CredentialSubjectType(StrEnum):
    PRINCIPAL = "principal"
    ROLE = "role"
    TENANT = "tenant"


class CredentialInjectionLocation(StrEnum):
    HEADER = "header"
    QUERY = "query"


class CredentialValueFormat(StrEnum):
    RAW = "raw"
    BEARER = "bearer"


class CredentialBindingStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class SecretReference:
    """只描述 Secret 的保存位置，不包含 Secret Value。"""

    provider: str
    reference: str
    version: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.reference.strip():
            raise ValueError("secret reference provider and reference must not be blank")
        if "://" in self.reference:
            raise ValueError("secret reference must be opaque and must not contain a URL")


class SecretValue:
    """只在单次执行内存中短暂存在，字符串表示永远脱敏。"""

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        if not value:
            raise ValueError("secret value must not be empty")
        self.__value = value

    def reveal(self) -> str:
        """仅允许 Credential Injection Adapter 在最后时刻调用。"""

        return self.__value

    def __repr__(self) -> str:
        return "SecretValue('[REDACTED]')"

    def __str__(self) -> str:
        return "[REDACTED]"


@dataclass(frozen=True, slots=True)
class CredentialBinding:
    id: str
    tenant_id: str
    subject_type: CredentialSubjectType
    subject_id: str | None
    tool_id: str | None
    upstream_service_id: str
    secret_reference: SecretReference
    injection_location: CredentialInjectionLocation
    injection_name: str
    value_format: CredentialValueFormat
    status: CredentialBindingStatus = CredentialBindingStatus.ACTIVE

    def __post_init__(self) -> None:
        if self.subject_type is CredentialSubjectType.TENANT and self.subject_id is not None:
            raise ValueError("tenant credential subject must not declare subject id")
        if self.subject_type is not CredentialSubjectType.TENANT and not self.subject_id:
            raise ValueError("principal or role credential subject must declare subject id")
        if not self.injection_name.strip():
            raise ValueError("credential injection name must not be blank")


@dataclass(frozen=True, slots=True)
class ResolvedCredential:
    """只在单次 Executor 调用期间存在，不允许进入 Persistence/Audit。"""

    credential_binding_id: str
    injection_location: CredentialInjectionLocation
    injection_name: str
    value_format: CredentialValueFormat
    value: SecretValue
