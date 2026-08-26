"""应用错误码与安全消息契约测试。"""

import pytest

from nexusmcp.shared.errors import (
    BindingDigestMismatchError,
    ImportedOperationNotFoundError,
    InvalidArgumentsError,
    InvalidReviewStateError,
    InvalidToolStateError,
    NexusMcpError,
    OpenApiDocumentInvalidError,
    OpenApiFeatureUnsupportedError,
    OpenApiSourceNotFoundError,
    PublishConflictError,
    SchemaDigestMismatchError,
    TenantBoundaryViolationError,
    ToolBindingNotFoundError,
    ToolNotFoundError,
    ToolVersionNotFoundError,
    UpstreamNotActiveError,
)


@pytest.mark.parametrize(
    "error_type",
    [
        ToolNotFoundError,
        ToolVersionNotFoundError,
        ToolBindingNotFoundError,
        InvalidToolStateError,
        TenantBoundaryViolationError,
        PublishConflictError,
        UpstreamNotActiveError,
        SchemaDigestMismatchError,
        BindingDigestMismatchError,
        OpenApiSourceNotFoundError,
        OpenApiDocumentInvalidError,
        OpenApiFeatureUnsupportedError,
        ImportedOperationNotFoundError,
        InvalidReviewStateError,
        InvalidArgumentsError,
    ],
)
def test_error_contract_uses_stable_code_and_safe_english_message(
    error_type: type[NexusMcpError],
) -> None:
    error = error_type("internal diagnosis")

    assert error.code.isascii()
    assert error.code == error.code.lower()
    assert "_" in error.code
    assert error.safe_message.endswith(".")
    assert "internal diagnosis" not in error.safe_message


def test_internal_message_is_available_only_on_exception_object() -> None:
    error = PublishConflictError("constraint uq_tool_version_one_published failed")

    assert "uq_tool_version" in str(error)
    assert "uq_tool_version" not in error.safe_message
