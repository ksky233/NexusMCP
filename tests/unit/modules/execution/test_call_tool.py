"""Read-Only CallTool 编排、拒绝与 Execution 终态测试。"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from nexusmcp.modules.approval.domain import ApprovalStatus
from nexusmcp.modules.approval.use_cases import (
    DecideApproval,
    DecideApprovalCommand,
    GetApproval,
    GetApprovalQuery,
    RequestApproval,
)
from nexusmcp.modules.catalog.domain import ToolSideEffect, ToolVisibility
from nexusmcp.modules.connectors.domain import ToolBindingType
from nexusmcp.modules.credentials.domain import (
    CredentialBinding,
    CredentialInjectionLocation,
    CredentialSubjectType,
    CredentialValueFormat,
    ResolvedCredential,
    SecretReference,
    SecretValue,
)
from nexusmcp.modules.execution.adapters.in_memory import InMemoryToolExecutionRepository
from nexusmcp.modules.execution.adapters.in_memory_uow import (
    InMemoryExecutionUnitOfWorkFactory,
)
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
from nexusmcp.modules.execution.lifecycle import ExecutionLifecycle
from nexusmcp.modules.identity.adapters.context_principal import ContextPrincipalResolver
from nexusmcp.modules.policy.adapters.static_read_only import StaticReadOnlyPolicyEvaluator
from nexusmcp.modules.policy.domain import (
    PolicyDecision,
    PolicyEffect,
    PolicyEvaluationInput,
)
from nexusmcp.shared.errors import (
    ApprovalRequiredError,
    AuthorizationError,
    CredentialBindingNotFoundError,
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
    def __init__(self) -> None:
        self._count = 0

    def new_id(self) -> str:
        self._count += 1
        return "execution-1" if self._count == 1 else f"audit-{self._count - 1}"


class FixedApprovalIdentifierGenerator:
    def new_id(self) -> str:
        return "approval-1"


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


class CapturingExecutor:
    def __init__(self) -> None:
        self.credential: ResolvedCredential | None = None

    async def execute(
        self,
        request: ExecutorRequest,
        credential: ResolvedCredential | None,
    ) -> ExecutorResult:
        self.credential = credential
        return ExecutorResult(
            data={"employee_id": request.arguments["employee_id"]},
            content_type="application/json",
            upstream_status=200,
        )


class CountingCredentialResolver:
    def __init__(self, resolved: CredentialBinding | None) -> None:
        self._resolved = resolved
        self.calls = 0

    async def resolve(
        self,
        tenant_id: str,
        principal: object,
        tool_id: str,
        upstream_service_id: str,
    ) -> CredentialBinding | None:
        _ = (tenant_id, principal, tool_id, upstream_service_id)
        self.calls += 1
        return self._resolved


class CountingCredentialProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def resolve(self, reference: SecretReference) -> SecretValue:
        _ = reference
        self.calls += 1
        return SecretValue("upstream-secret")


class RequireApprovalEvaluator:
    async def evaluate(self, policy_input: PolicyEvaluationInput) -> PolicyDecision:
        _ = policy_input
        return PolicyDecision(
            effect=PolicyEffect.REQUIRE_APPROVAL,
            policy_version="policy-v1",
            reason_code="human_confirmation_required",
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
    *,
    auth_scheme: str | None = "none",
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
        upstream_auth_scheme=auth_scheme,
    )


def build_use_case(
    *,
    tool: ResolvedExecutableTool | None = None,
    executor: SuccessfulExecutor
    | CapturingExecutor
    | UnknownExecutor
    | CancelledExecutor
    | None = None,
    credential_binding_resolver: CountingCredentialResolver | None = None,
    credential_provider: CountingCredentialProvider | None = None,
    policy_evaluator: StaticReadOnlyPolicyEvaluator | RequireApprovalEvaluator | None = None,
    request_approval: RequestApproval | None = None,
    unit_of_work_factory: InMemoryExecutionUnitOfWorkFactory | None = None,
) -> tuple[CallTool, InMemoryToolExecutionRepository]:
    resolved_factory = unit_of_work_factory or InMemoryExecutionUnitOfWorkFactory()
    identifier_generator = FixedIdentifierGenerator()
    resolved_tool = tool or executable_tool()
    return (
        CallTool(
            principal_resolver=ContextPrincipalResolver(),
            tool_resolver=StaticResolver(resolved_tool),
            arguments_validator=JsonSchemaArgumentsValidator(),
            policy_evaluator=policy_evaluator or StaticReadOnlyPolicyEvaluator(),
            execution_lifecycle=ExecutionLifecycle(
                resolved_factory,
                FixedClock(),
                identifier_generator,
            ),
            executor=executor or SuccessfulExecutor(),
            credential_binding_resolver=credential_binding_resolver,
            credential_provider=credential_provider,
            request_approval=request_approval,
        ),
        resolved_factory.execution_reader,
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
async def test_allowed_call_resolves_credential_and_records_only_binding_id() -> None:
    credential_binding = CredentialBinding(
        id="credential-binding-1",
        tenant_id="tenant-a",
        subject_type=CredentialSubjectType.TENANT,
        subject_id=None,
        tool_id="tool-1",
        upstream_service_id="upstream-1",
        secret_reference=SecretReference(
            provider="environment",
            reference="EMPLOYEE_API_TOKEN",
        ),
        injection_location=CredentialInjectionLocation.HEADER,
        injection_name="Authorization",
        value_format=CredentialValueFormat.BEARER,
    )
    resolver = CountingCredentialResolver(credential_binding)
    provider = CountingCredentialProvider()
    executor = CapturingExecutor()
    use_case, repository = build_use_case(
        tool=executable_tool(auth_scheme="bearer"),
        executor=executor,
        credential_binding_resolver=resolver,
        credential_provider=provider,
    )

    result = await use_case.execute(
        CallToolCommand(
            context=context(),
            tool_name="directory.get_employee",
            arguments={"employee_id": "emp-001"},
        )
    )

    execution = await repository.get_by_id("tenant-a", result.execution_id)
    assert resolver.calls == 1
    assert provider.calls == 1
    assert executor.credential is not None
    assert executor.credential.value.reveal() == "upstream-secret"
    assert execution is not None
    assert execution.credential_binding_id == "credential-binding-1"
    assert "upstream-secret" not in repr(execution)


@pytest.mark.asyncio
async def test_denied_call_does_not_resolve_or_read_credential() -> None:
    resolver = CountingCredentialResolver(None)
    provider = CountingCredentialProvider()
    use_case, repository = build_use_case(
        tool=executable_tool(
            ToolSideEffect.NON_IDEMPOTENT_WRITE,
            auth_scheme="bearer",
        ),
        credential_binding_resolver=resolver,
        credential_provider=provider,
    )

    with pytest.raises(AuthorizationError):
        await use_case.execute(
            CallToolCommand(
                context=context(),
                tool_name="directory.get_employee",
                arguments={"employee_id": "emp-001"},
            )
        )

    assert resolver.calls == 0
    assert provider.calls == 0
    assert await repository.list_by_tenant("tenant-a") == ()


@pytest.mark.asyncio
async def test_missing_credential_binding_fails_before_execution_record() -> None:
    resolver = CountingCredentialResolver(None)
    provider = CountingCredentialProvider()
    use_case, repository = build_use_case(
        tool=executable_tool(auth_scheme="bearer"),
        credential_binding_resolver=resolver,
        credential_provider=provider,
    )

    with pytest.raises(CredentialBindingNotFoundError):
        await use_case.execute(
            CallToolCommand(
                context=context(),
                tool_name="directory.get_employee",
                arguments={"employee_id": "emp-001"},
            )
        )

    assert resolver.calls == 1
    assert provider.calls == 0
    assert await repository.list_by_tenant("tenant-a") == ()


@pytest.mark.asyncio
async def test_required_approval_pauses_then_consumes_before_credential() -> None:
    approval_factory = InMemoryExecutionUnitOfWorkFactory()
    requester = RequestApproval(approval_factory, FixedClock(), FixedApprovalIdentifierGenerator())
    decider = DecideApproval(approval_factory, FixedClock(), FixedIdentifierGenerator())
    reader = GetApproval(approval_factory)
    credential_resolver = CountingCredentialResolver(
        CredentialBinding(
            id="credential-binding-approval",
            tenant_id="tenant-a",
            subject_type=CredentialSubjectType.TENANT,
            subject_id=None,
            tool_id="tool-1",
            upstream_service_id="upstream-1",
            secret_reference=SecretReference(
                provider="environment",
                reference="EMPLOYEE_API_TOKEN",
            ),
            injection_location=CredentialInjectionLocation.HEADER,
            injection_name="Authorization",
            value_format=CredentialValueFormat.BEARER,
        )
    )
    credential_provider = CountingCredentialProvider()
    use_case, repository = build_use_case(
        tool=executable_tool(auth_scheme="bearer"),
        policy_evaluator=RequireApprovalEvaluator(),
        request_approval=requester,
        unit_of_work_factory=approval_factory,
        credential_binding_resolver=credential_resolver,
        credential_provider=credential_provider,
    )
    command = CallToolCommand(
        context=context(),
        tool_name="directory.get_employee",
        arguments={"employee_id": "emp-001"},
    )

    with pytest.raises(ApprovalRequiredError) as captured:
        await use_case.execute(command)

    approval_id = captured.value.approval_id
    assert approval_id == "approval-1"
    assert credential_resolver.calls == 0
    assert credential_provider.calls == 0
    assert await repository.list_by_tenant("tenant-a") == ()

    await decider.execute(
        DecideApprovalCommand(
            context=context(),
            approval_id=approval_id,
            approved=True,
        )
    )
    result = await use_case.execute(
        CallToolCommand(
            context=context(),
            tool_name=command.tool_name,
            arguments=command.arguments,
            approval_id=approval_id,
        )
    )
    approval = await reader.execute(GetApprovalQuery(context=context(), approval_id=approval_id))

    assert result.data["employee_id"] == "emp-001"
    assert approval.status is ApprovalStatus.CONSUMED
    assert credential_resolver.calls == 1
    assert credential_provider.calls == 1


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
