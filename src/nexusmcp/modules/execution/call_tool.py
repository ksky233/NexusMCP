"""S3-1 Read-Only HTTP Tool Call Application Use Case。"""

import asyncio

from nexusmcp.modules.approval.use_cases import (
    ConsumeApproval,
    ConsumeApprovalCommand,
    RequestApproval,
    RequestApprovalCommand,
)
from nexusmcp.modules.catalog.domain import ToolVisibility
from nexusmcp.modules.credentials.domain import ResolvedCredential
from nexusmcp.modules.credentials.ports import CredentialBindingResolver, CredentialProvider
from nexusmcp.modules.execution.domain import (
    CallToolCommand,
    CallToolResult,
    ExecutionErrorCategory,
    ExecutionStatus,
    ExecutorFailure,
    ExecutorRequest,
    ResolvedExecutableTool,
    ToolExecution,
)
from nexusmcp.modules.execution.ports import (
    ArgumentsValidator,
    ExecutableToolResolver,
    ToolExecutionRepository,
    ToolExecutor,
)
from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.modules.identity.ports import PrincipalResolver
from nexusmcp.modules.policy.domain import (
    PolicyEffect,
    PolicyEvaluationInput,
    ToolAction,
)
from nexusmcp.modules.policy.ports import PolicyEvaluator
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import (
    ApprovalRequiredError,
    AuthorizationError,
    CredentialBindingNotFoundError,
    CredentialResolutionError,
    InvalidArgumentsError,
    ToolNotFoundError,
    ToolNotVisibleError,
    UnknownExecutionOutcomeError,
    UpstreamResponseError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from nexusmcp.shared.identifiers import IdentifierGenerator


class CallTool:
    def __init__(
        self,
        *,
        principal_resolver: PrincipalResolver,
        tool_resolver: ExecutableToolResolver,
        arguments_validator: ArgumentsValidator,
        policy_evaluator: PolicyEvaluator,
        execution_repository: ToolExecutionRepository,
        executor: ToolExecutor,
        clock: Clock,
        identifier_generator: IdentifierGenerator,
        credential_binding_resolver: CredentialBindingResolver | None = None,
        credential_provider: CredentialProvider | None = None,
        request_approval: RequestApproval | None = None,
        consume_approval: ConsumeApproval | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("tool call timeout must be positive")
        self._principal_resolver = principal_resolver
        self._tool_resolver = tool_resolver
        self._arguments_validator = arguments_validator
        self._policy_evaluator = policy_evaluator
        self._execution_repository = execution_repository
        self._executor = executor
        self._clock = clock
        self._identifier_generator = identifier_generator
        self._credential_binding_resolver = credential_binding_resolver
        self._credential_provider = credential_provider
        self._request_approval = request_approval
        self._consume_approval = consume_approval
        self._timeout_seconds = timeout_seconds

    async def execute(self, command: CallToolCommand) -> CallToolResult:
        context = command.context
        principal = await self._principal_resolver.resolve(context)
        tool = await self._tool_resolver.resolve(context.tenant_id, command.tool_name)
        if tool is None:
            raise ToolNotFoundError(f"tool {command.tool_name} was not executable in tenant")
        if not _is_visible(tool.visibility, principal.principal_type):
            raise ToolNotVisibleError(f"tool {command.tool_name} was not visible to principal")

        self._arguments_validator.validate(tool.input_schema, command.arguments)
        policy_input = PolicyEvaluationInput(
            tenant_id=context.tenant_id,
            principal=principal,
            tool_id=tool.tool_id,
            tool_version_id=tool.tool_version_id,
            action=ToolAction.CALL,
            side_effect=tool.side_effect,
            arguments_digest=command.arguments_digest,
        )
        decision = await self._policy_evaluator.evaluate(policy_input)
        if decision.effect is PolicyEffect.DENY:
            raise AuthorizationError(f"policy denied call with reason {decision.reason_code}")
        if decision.effect is PolicyEffect.REQUIRE_APPROVAL:
            await self._pass_approval_gate(
                command=command,
                principal=principal,
                tool=tool,
                policy_version=decision.policy_version,
                reason_code=decision.reason_code,
            )

        tenant_id = context.tenant_id
        credential = await self._resolve_credential(
            tenant_id=tenant_id,
            principal=principal,
            tool=tool,
        )
        execution = ToolExecution(
            id=self._identifier_generator.new_id(),
            tenant_id=tenant_id,
            principal_id=principal.id,
            tool_id=tool.tool_id,
            tool_version_id=tool.tool_version_id,
            tool_binding_id=tool.tool_binding_id,
            arguments_digest=command.arguments_digest,
            side_effect=tool.side_effect,
            status=ExecutionStatus.PLANNED,
            planned_at=self._clock.now(),
            credential_binding_id=(
                credential.credential_binding_id if credential is not None else None
            ),
            idempotency_key=command.idempotency_key,
        )
        await self._execution_repository.add(tenant_id, execution)
        execution = execution.start(self._clock.now())
        await self._execution_repository.save(tenant_id, execution)

        try:
            executor_result = await self._executor.execute(
                ExecutorRequest(
                    execution_id=execution.id,
                    tool=tool,
                    arguments=command.arguments,
                    timeout_seconds=self._timeout_seconds,
                ),
                credential=credential,
            )
        except asyncio.CancelledError:
            await self._execution_repository.save(
                tenant_id,
                execution.cancel(self._clock.now()),
            )
            raise
        except ExecutorFailure as error:
            if error.outcome_unknown:
                terminal = execution.mark_unknown(
                    error_code=error.code,
                    finished_at=self._clock.now(),
                )
            else:
                terminal = execution.fail(
                    error_code=error.code,
                    category=error.category,
                    finished_at=self._clock.now(),
                )
            await self._execution_repository.save(tenant_id, terminal)
            raise _public_executor_error(error) from None
        except Exception as error:
            await self._execution_repository.save(
                tenant_id,
                execution.mark_unknown(
                    error_code="unexpected_executor_failure",
                    finished_at=self._clock.now(),
                ),
            )
            raise UnknownExecutionOutcomeError("unexpected executor failure") from error

        await self._execution_repository.save(
            tenant_id,
            execution.succeed(self._clock.now()),
        )
        return CallToolResult(
            execution_id=execution.id,
            data=executor_result.data,
            content_type=executor_result.content_type,
            upstream_status=executor_result.upstream_status,
        )

    async def _pass_approval_gate(
        self,
        *,
        command: CallToolCommand,
        principal: InternalPrincipal,
        tool: ResolvedExecutableTool,
        policy_version: str,
        reason_code: str,
    ) -> None:
        if self._request_approval is None or self._consume_approval is None:
            raise ApprovalRequiredError(f"policy requires approval with reason {reason_code}")
        if command.approval_id is None:
            approval = await self._request_approval.execute(
                RequestApprovalCommand(
                    context=command.context,
                    principal_id=principal.id,
                    tool_id=tool.tool_id,
                    tool_version_id=tool.tool_version_id,
                    arguments_digest=command.arguments_digest,
                    policy_version=policy_version,
                )
            )
            raise ApprovalRequiredError(
                f"policy requires approval with reason {reason_code}",
                approval_id=approval.id,
                expires_at=approval.expires_at.isoformat(),
            )
        await self._consume_approval.execute(
            ConsumeApprovalCommand(
                context=command.context,
                approval_id=command.approval_id,
                principal_id=principal.id,
                tool_version_id=tool.tool_version_id,
                arguments_digest=command.arguments_digest,
                policy_version=policy_version,
            )
        )

    async def _resolve_credential(
        self,
        *,
        tenant_id: str,
        principal: InternalPrincipal,
        tool: ResolvedExecutableTool,
    ) -> ResolvedCredential | None:
        auth_scheme = (tool.upstream_auth_scheme or "none").strip().lower()
        if auth_scheme == "none":
            return None
        if self._credential_binding_resolver is None or self._credential_provider is None:
            raise CredentialResolutionError("credential services were not configured")

        binding = await self._credential_binding_resolver.resolve(
            tenant_id,
            principal,
            tool.tool_id,
            tool.upstream_service_id,
        )
        if binding is None:
            raise CredentialBindingNotFoundError("no credential binding matched tool call")
        value = await self._credential_provider.resolve(binding.secret_reference)
        return ResolvedCredential(
            credential_binding_id=binding.id,
            injection_location=binding.injection_location,
            injection_name=binding.injection_name,
            value_format=binding.value_format,
            value=value,
        )


def _is_visible(visibility: ToolVisibility, principal_type: PrincipalType) -> bool:
    if visibility is ToolVisibility.PUBLIC:
        return True
    if visibility is ToolVisibility.AUTHENTICATED:
        return principal_type is not PrincipalType.ANONYMOUS
    return False


def _public_executor_error(error: ExecutorFailure) -> Exception:
    if error.outcome_unknown:
        return UnknownExecutionOutcomeError(error.code)
    if error.category in {
        ExecutionErrorCategory.VALIDATION,
    }:
        return InvalidArgumentsError(error.code)
    if error.category is ExecutionErrorCategory.AUTHORIZATION:
        return AuthorizationError(error.code)
    if error.category in {
        ExecutionErrorCategory.TIMEOUT_BEFORE_SEND,
        ExecutionErrorCategory.TIMEOUT_AFTER_SEND,
    }:
        return UpstreamTimeoutError(error.code)
    if error.category in {
        ExecutionErrorCategory.NETWORK,
        ExecutionErrorCategory.UPSTREAM_5XX,
    }:
        return UpstreamUnavailableError(error.code)
    return UpstreamResponseError(error.code)
