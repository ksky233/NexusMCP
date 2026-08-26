"""Read-Only CallTool 编排、拒绝与 Execution 终态测试。"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from nexusmcp.modules.catalog.domain import ToolSideEffect, ToolVisibility
from nexusmcp.modules.connectors.domain import ToolBindingType
from nexusmcp.modules.credentials.domain import ResolvedCredential
from nexusmcp.modules.execution.adapters.in_memory import InMemoryToolExecutionRepository
from nexusmcp.modules.execution.adapters.jsonschema_validator import JsonSchemaArgumentsValidator
from nexusmcp.modules.execution.call_tool import CallTool
from nexusmcp.modules.execution.domain import (
    CallToolCommand,
    ExecutionErrorCategory,
    ExecutionStatus,
    ExecutorFailure,
    ExecutorRequest,
    ExecutorResult,
    ResolvedExecutableTool,
)
from nexusmcp.modules.identity.adapters.context_principal import ContextPrincipalResolver
from nexusmcp.modules.policy.adapters.static_read_only import StaticReadOnlyPolicyEvaluator
from nexusmcp.shared.errors import (
    AuthorizationError,
    InvalidArgumentsError,
    UnknownExecutionOutcomeError,
)
from nexusmcp.shared.request_context import ActorContext

NOW = datetime(2026, 8, 26, 15, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    def now(self) -> datetime:
        return NOW


class FixedIdentifierGenerator:
    def new_id(self) -> str:
        return "execution-1"


class StaticResolver:
    def __init__(self, tool: ResolvedExecutableTool) -> None:
        self._tool = tool

    async def resolve(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> ResolvedExecutableTool | None:
        if tenant_id == self._tool.tenant_id and canonical_name == self._tool.canonical_name:
            return self._tool
        return None


class SuccessfulExecutor:
    async def execute(
        self,
        request: ExecutorRequest,
        credential: ResolvedCredential | None,
    ) -> ExecutorResult:
        _ = credential
        return ExecutorResult(
            data={"employee_id": request.arguments["employee_id"], "name": "Ada Chen"},
            content_type="application/json",
            upstream_status=200,
        )


class UnknownExecutor:
    async def execute(
        self,
        request: ExecutorRequest,
        credential: ResolvedCredential | None,
    ) -> ExecutorResult:
        _ = (request, credential)
        raise ExecutorFailure(
            code="response_lost_after_send",
            category=ExecutionErrorCategory.TIMEOUT_AFTER_SEND,
            outcome_unknown=True,
        )


class CancelledExecutor:
    async def execute(
        self,
        request: ExecutorRequest,
        credential: ResolvedCredential | None,
    ) -> ExecutorResult:
        _ = (request, credential)
        raise asyncio.CancelledError


def context() -> ActorContext:
    return ActorContext(
        request_id="request-call",
        trace_id="a" * 32,
        tenant_id="tenant-a",
        principal_id="anonymous",
        authn_method="anonymous",
    )


def executable_tool(
    side_effect: ToolSideEffect = ToolSideEffect.READ_ONLY,
) -> ResolvedExecutableTool:
    return ResolvedExecutableTool(
        tenant_id="tenant-a",
        tool_id="tool-1",
        tool_version_id="version-1",
        tool_binding_id="binding-1",
        upstream_service_id="upstream-1",
        canonical_name="directory.get_employee",
        version=1,
        input_schema={
            "type": "object",
            "properties": {"employee_id": {"type": "string", "minLength": 1}},
            "required": ["employee_id"],
            "additionalProperties": False,
        },
        output_schema=None,
        side_effect=side_effect,
        visibility=ToolVisibility.PUBLIC,
        binding_type=ToolBindingType.HTTP,
        binding_config={
            "method": "GET",
            "path_template": "/employees/{employee_id}",
            "parameters": [
                {
                    "argument_name": "employee_id",
                    "upstream_name": "employee_id",
                    "location": "path",
                    "required": True,
                }
            ],
            "request_body": None,
        },
        upstream_endpoint="http://employee.test",
    )


def build_use_case(
    *,
    tool: ResolvedExecutableTool | None = None,
    executor: SuccessfulExecutor | UnknownExecutor | CancelledExecutor | None = None,
) -> tuple[CallTool, InMemoryToolExecutionRepository]:
    repository = InMemoryToolExecutionRepository()
    resolved_tool = tool or executable_tool()
    return (
        CallTool(
            principal_resolver=ContextPrincipalResolver(),
            tool_resolver=StaticResolver(resolved_tool),
            arguments_validator=JsonSchemaArgumentsValidator(),
            policy_evaluator=StaticReadOnlyPolicyEvaluator(),
            execution_repository=repository,
            executor=executor or SuccessfulExecutor(),
            clock=FixedClock(),
            identifier_generator=FixedIdentifierGenerator(),
        ),
        repository,
    )


@pytest.mark.asyncio
async def test_read_only_call_succeeds_and_records_execution() -> None:
    use_case, repository = build_use_case()

    result = await use_case.execute(
        CallToolCommand(
            context=context(),
            tool_name="directory.get_employee",
            arguments={"employee_id": "emp-001"},
        )
    )

    execution = await repository.get_by_id("tenant-a", result.execution_id)
    assert result.data["employee_id"] == "emp-001"
    assert execution is not None and execution.status is ExecutionStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_invalid_arguments_are_rejected_before_execution_record() -> None:
    use_case, repository = build_use_case()

    with pytest.raises(InvalidArgumentsError):
        await use_case.execute(
            CallToolCommand(
                context=context(),
                tool_name="directory.get_employee",
                arguments={},
            )
        )

    assert await repository.list_by_tenant("tenant-a") == ()


@pytest.mark.asyncio
async def test_static_policy_denies_write_tool_before_execution() -> None:
    use_case, repository = build_use_case(tool=executable_tool(ToolSideEffect.NON_IDEMPOTENT_WRITE))

    with pytest.raises(AuthorizationError):
        await use_case.execute(
            CallToolCommand(
                context=context(),
                tool_name="directory.get_employee",
                arguments={"employee_id": "emp-001"},
            )
        )

    assert await repository.list_by_tenant("tenant-a") == ()


@pytest.mark.asyncio
async def test_unknown_executor_outcome_is_persisted_before_safe_error() -> None:
    use_case, repository = build_use_case(executor=UnknownExecutor())

    with pytest.raises(UnknownExecutionOutcomeError):
        await use_case.execute(
            CallToolCommand(
                context=context(),
                tool_name="directory.get_employee",
                arguments={"employee_id": "emp-001"},
            )
        )

    execution = await repository.get_by_id("tenant-a", "execution-1")
    assert execution is not None and execution.status is ExecutionStatus.UNKNOWN


@pytest.mark.asyncio
async def test_cancel_is_persisted_and_propagated() -> None:
    use_case, repository = build_use_case(executor=CancelledExecutor())

    with pytest.raises(asyncio.CancelledError):
        await use_case.execute(
            CallToolCommand(
                context=context(),
                tool_name="directory.get_employee",
                arguments={"employee_id": "emp-001"},
            )
        )

    execution = await repository.get_by_id("tenant-a", "execution-1")
    assert execution is not None and execution.status is ExecutionStatus.CANCELLED
