"""Environment Credential Provider 的安全解析边界测试。"""

import pytest

from nexusmcp.modules.credentials.adapters.environment import EnvironmentCredentialProvider
from nexusmcp.modules.credentials.domain import SecretReference
from nexusmcp.shared.errors import CredentialResolutionError


@pytest.mark.asyncio
async def test_environment_provider_resolves_secret_without_exposing_repr() -> None:
    provider = EnvironmentCredentialProvider({"EMPLOYEE_API_TOKEN": "upstream-secret"})

    value = await provider.resolve(
        SecretReference(provider="environment", reference="EMPLOYEE_API_TOKEN")
    )

    assert value.reveal() == "upstream-secret"
    assert "upstream-secret" not in repr(value)
    assert "upstream-secret" not in str(value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reference",
    [
        SecretReference(provider="vault", reference="EMPLOYEE_API_TOKEN"),
        SecretReference(provider="environment", reference="employee_api_token"),
        SecretReference(provider="environment", reference="MISSING_API_TOKEN"),
    ],
)
async def test_environment_provider_fails_closed_with_safe_error(
    reference: SecretReference,
) -> None:
    provider = EnvironmentCredentialProvider({})

    with pytest.raises(CredentialResolutionError) as captured:
        await provider.resolve(reference)

    assert captured.value.code == "credential_resolution_failed"
    assert reference.reference not in str(captured.value)
