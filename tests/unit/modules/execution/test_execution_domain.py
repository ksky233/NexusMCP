"""Call Digest、Execution 状态机与 Retry Matrix 测试。"""

from datetime import UTC, datetime, timedelta

import pytest

from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.execution.domain import (
    CallToolCommand,
    ExecutionErrorCategory,
    ExecutionStatus,
    RetryDisposition,
    ToolExecution,
    retry_disposition,
)
from nexusmcp.shared.request_context import ActorContext

NOW = datetime(2026, 8, 26, 13, 0, tzinfo=UTC)


def _context() -> ActorContext:
    return ActorContext(
        request_id="request-call",
        trace_id="9" * 32,
        tenant_id="tenant-a",
        principal_id="user-a",
        authn_method="test",
    )


def _execution() -> ToolExecution:
    return ToolExecution(
        id="execution-1",
        tenant_id="tenant-a",
        request_id="request-1",
        trace_id="a" * 32,
        principal_id="user-a",
        tool_id="tool-1",
        tool_version_id="version-1",
        tool_binding_id="binding-1",
        arguments_digest="1" * 64,
        policy_version="policy-v1",
        policy_reason_code="allowed",
        side_effect=ToolSideEffect.NON_IDEMPOTENT_WRITE,
        status=ExecutionStatus.PLANNED,
        planned_at=NOW,
    )


def test_argument_digest_is_stable_across_mapping_key_order() -> None:
    first = CallToolCommand(
        context=_context(),
        tool_name="inventory.reserve_stock",
        arguments={"sku": "laptop", "body": {"quantity": 2, "warehouse": "shanghai"}},
    )
    second = CallToolCommand(
        context=_context(),
        tool_name="inventory.reserve_stock",
        arguments={"body": {"warehouse": "shanghai", "quantity": 2}, "sku": "laptop"},
    )

    assert first.arguments_digest == second.arguments_digest


@pytest.mark.parametrize("key", ["", " leading", "line\nbreak", "中文-key", "a" * 129])
def test_idempotency_key_accepts_only_bounded_safe_token_characters(key: str) -> None:
    with pytest.raises(ValueError, match="idempotency key"):
        CallToolCommand(
            context=_context(),
            tool_name="inventory.set_reorder_level",
            arguments={},
            idempotency_key=key,
        )


def test_unknown_outcome_is_distinct_from_known_failure() -> None:
    running = _execution().start(NOW + timedelta(seconds=1))
    failed = running.fail(
        error_code="upstream_400",
        category=ExecutionErrorCategory.UPSTREAM_4XX,
        finished_at=NOW + timedelta(seconds=2),
    )
    unknown = running.mark_unknown(
        error_code="response_lost_after_send",
        finished_at=NOW + timedelta(seconds=2),
    )

    assert failed.status is ExecutionStatus.FAILED
    assert unknown.status is ExecutionStatus.UNKNOWN
    with pytest.raises(ValueError, match="running"):
        failed.succeed(NOW + timedelta(seconds=3))


@pytest.mark.parametrize(
    ("side_effect", "category", "has_key", "expected"),
    [
        (
            ToolSideEffect.READ_ONLY,
            ExecutionErrorCategory.NETWORK,
            False,
            RetryDisposition.RETRY,
        ),
        (
            ToolSideEffect.READ_ONLY,
            ExecutionErrorCategory.TIMEOUT_AFTER_SEND,
            False,
            RetryDisposition.RETRY,
        ),
        (
            ToolSideEffect.IDEMPOTENT_WRITE,
            ExecutionErrorCategory.UPSTREAM_5XX,
            True,
            RetryDisposition.RETRY,
        ),
        (
            ToolSideEffect.IDEMPOTENT_WRITE,
            ExecutionErrorCategory.UPSTREAM_5XX,
            False,
            RetryDisposition.DO_NOT_RETRY,
        ),
        (
            ToolSideEffect.NON_IDEMPOTENT_WRITE,
            ExecutionErrorCategory.TIMEOUT_AFTER_SEND,
            False,
            RetryDisposition.REQUIRE_RECONCILIATION,
        ),
        (
            ToolSideEffect.READ_ONLY,
            ExecutionErrorCategory.VALIDATION,
            False,
            RetryDisposition.DO_NOT_RETRY,
        ),
    ],
)
def test_retry_matrix(
    side_effect: ToolSideEffect,
    category: ExecutionErrorCategory,
    has_key: bool,
    expected: RetryDisposition,
) -> None:
    assert (
        retry_disposition(
            side_effect=side_effect,
            error_category=category,
            has_idempotency_key=has_key,
        )
        is expected
    )
