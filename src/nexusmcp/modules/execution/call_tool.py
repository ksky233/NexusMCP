"""S3-1 Read-Only HTTP Tool Call Application Use Case。"""

import asyncio

from nexusmcp.modules.catalog.domain import ToolVisibility
from nexusmcp.modules.execution.domain import (
    CallToolCommand,
    CallToolResult,
    ExecutionErrorCategory,
    ExecutionStatus,
    ExecutorFailure,
    ExecutorRequest,
    ToolExecution,
)
from nexusmcp.modules.execution.ports import (
    ArgumentsValidator,
    ExecutableToolResolver,
    ToolExecutionRepository,
    ToolExecutor,
)
from nexusmcp.modules.identity.domain import PrincipalType
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
            raise ApprovalRequiredError(
                f"policy requires approval with reason {decision.reason_code}"
            )

        tenant_id = context.tenant_id
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
                credential=None,
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
