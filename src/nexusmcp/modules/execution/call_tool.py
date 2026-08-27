"""Tool Call 的 Policy、Approval、Credential 与 Execution 主编排。"""

import asyncio

from nexusmcp.modules.approval.use_cases import (
    RequestApproval,
    RequestApprovalCommand,
)
from nexusmcp.modules.audit.domain import AuditOutcome
from nexusmcp.modules.catalog.domain import ToolSideEffect, ToolVisibility
from nexusmcp.modules.credentials.domain import CredentialBinding, ResolvedCredential
from nexusmcp.modules.credentials.ports import CredentialBindingResolver, CredentialProvider
from nexusmcp.modules.execution.domain import (
    CallToolCommand,
    CallToolResult,
    ExecutionErrorCategory,
    ExecutorFailure,
    ExecutorRequest,
    ResolvedExecutableTool,
)
from nexusmcp.modules.execution.lifecycle import (
    ExecutionLifecycle,
    PlanExecutionCommand,
    RecordCallDecisionCommand,
)
from nexusmcp.modules.execution.ports import (
    ArgumentsValidator,
    ExecutableToolResolver,
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
from nexusmcp.modules.registry.egress_ports import (
    AllowAllUpstreamEndpointPolicy,
    UpstreamEndpointPolicy,
)
from nexusmcp.shared.errors import (
    ApprovalRequiredError,
    AuthorizationError,
    CredentialBindingNotFoundError,
    CredentialResolutionError,
    IdempotencyKeyRequiredError,
    InvalidArgumentsError,
    NexusMcpError,
    ToolNotFoundError,
    ToolNotVisibleError,
    UnknownExecutionOutcomeError,
    UpstreamResponseError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)


class CallTool:
    def __init__(
        self,
        *,
        principal_resolver: PrincipalResolver,
        tool_resolver: ExecutableToolResolver,
        arguments_validator: ArgumentsValidator,
        policy_evaluator: PolicyEvaluator,
        execution_lifecycle: ExecutionLifecycle,
        executor: ToolExecutor,
        credential_binding_resolver: CredentialBindingResolver | None = None,
        credential_provider: CredentialProvider | None = None,
        request_approval: RequestApproval | None = None,
        upstream_endpoint_policy: UpstreamEndpointPolicy | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("tool call timeout must be positive")
        self._principal_resolver = principal_resolver
        self._tool_resolver = tool_resolver
        self._arguments_validator = arguments_validator
        self._policy_evaluator = policy_evaluator
        self._execution_lifecycle = execution_lifecycle
        self._executor = executor
        self._credential_binding_resolver = credential_binding_resolver
        self._credential_provider = credential_provider
        self._request_approval = request_approval
        self._upstream_endpoint_policy = (
            upstream_endpoint_policy or AllowAllUpstreamEndpointPolicy()
        )
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
        if (
            command.idempotency_key is not None
            and tool.side_effect is not ToolSideEffect.IDEMPOTENT_WRITE
        ):
            raise InvalidArgumentsError("idempotency key is only valid for idempotent write tools")
        if tool.side_effect is ToolSideEffect.IDEMPOTENT_WRITE and command.idempotency_key is None:
            raise IdempotencyKeyRequiredError("idempotent write call did not provide a key")
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
            await self._record_policy_decision(
                command=command,
                principal=principal,
                tool=tool,
                policy_version=decision.policy_version,
                reason_code=decision.reason_code,
                outcome=AuditOutcome.DENIED,
            )
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
        # Egress 必须在 Secret 解析和 Execution Plan 之前通过，拒绝危险目标时不接触 Credential。
        await self._upstream_endpoint_policy.validate(tool.upstream_endpoint)
        credential_binding = await self._resolve_credential_binding(
            tenant_id=tenant_id,
            principal=principal,
            tool=tool,
        )
        execution = await self._execution_lifecycle.plan(
            PlanExecutionCommand(
                context=context,
                principal_id=principal.id,
                tool_id=tool.tool_id,
                tool_version_id=tool.tool_version_id,
                tool_binding_id=tool.tool_binding_id,
                arguments_digest=command.arguments_digest,
                policy_version=decision.policy_version,
                policy_reason_code=decision.reason_code,
                side_effect=tool.side_effect,
                approval_id=(
                    command.approval_id
                    if decision.effect is PolicyEffect.REQUIRE_APPROVAL
                    else None
                ),
                credential_binding_id=(
                    credential_binding.id if credential_binding is not None else None
                ),
                idempotency_key=command.idempotency_key,
            )
        )
        try:
            credential = await self._resolve_secret(credential_binding)
        except NexusMcpError as error:
            await self._execution_lifecycle.fail(
                tenant_id,
                execution.id,
                error_code=error.code,
                category=ExecutionErrorCategory.CREDENTIAL,
            )
            raise
        except Exception as error:
            await self._execution_lifecycle.fail(
                tenant_id,
                execution.id,
                error_code="credential_resolution_failed",
                category=ExecutionErrorCategory.CREDENTIAL,
            )
            raise CredentialResolutionError("unexpected credential provider failure") from error

        try:
            executor_result = await self._executor.execute(
                ExecutorRequest(
                    execution_id=execution.id,
                    tool=tool,
                    arguments=command.arguments,
                    timeout_seconds=self._timeout_seconds,
                    idempotency_key=command.idempotency_key,
                ),
                credential=credential,
            )
        except asyncio.CancelledError:
            await self._execution_lifecycle.cancel(tenant_id, execution.id)
            raise
        except ExecutorFailure as error:
            await self._execution_lifecycle.fail(
                tenant_id,
                execution.id,
                error_code=error.code,
                category=error.category,
                outcome_unknown=error.outcome_unknown,
            )
            raise _public_executor_error(error) from None
        except Exception as error:
            await self._execution_lifecycle.fail(
                tenant_id,
                execution.id,
                error_code="unexpected_executor_failure",
                category=ExecutionErrorCategory.UNKNOWN,
                outcome_unknown=True,
            )
            raise UnknownExecutionOutcomeError("unexpected executor failure") from error

        terminal = await self._execution_lifecycle.succeed(tenant_id, execution.id)
        return CallToolResult(
            execution_id=execution.id,
            data=executor_result.data,
            content_type=executor_result.content_type,
            upstream_status=executor_result.upstream_status,
            attempt_count=terminal.attempt_count,
        )

    async def _record_policy_decision(
        self,
        *,
        command: CallToolCommand,
        principal: InternalPrincipal,
        tool: ResolvedExecutableTool,
        policy_version: str,
        reason_code: str,
        outcome: AuditOutcome,
    ) -> None:
        await self._execution_lifecycle.record_call_decision(
            RecordCallDecisionCommand(
                context=command.context,
                principal_id=principal.id,
                tool_version_id=tool.tool_version_id,
                arguments_digest=command.arguments_digest,
                policy_version=policy_version,
                reason_code=reason_code,
                outcome=outcome,
            )
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
        if command.approval_id is not None:
            # 真正消费由 ExecutionLifecycle 与 Running Execution 在同一事务中完成。
            return
        if self._request_approval is None:
            raise ApprovalRequiredError(f"policy requires approval with reason {reason_code}")
        approval = await self._request_approval.execute(
            RequestApprovalCommand(
                context=command.context,
                principal_id=principal.id,
                tool_id=tool.tool_id,
                tool_version_id=tool.tool_version_id,
                arguments_digest=command.arguments_digest,
                policy_version=policy_version,
                idempotency_key=command.idempotency_key,
                policy_reason_code=reason_code,
            )
        )
        raise ApprovalRequiredError(
            f"policy requires approval with reason {reason_code}",
            approval_id=approval.id,
            expires_at=approval.expires_at.isoformat(),
        )

    async def _resolve_credential_binding(
        self,
        *,
        tenant_id: str,
        principal: InternalPrincipal,
        tool: ResolvedExecutableTool,
    ) -> CredentialBinding | None:
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
        return binding

    async def _resolve_secret(
        self,
        binding: CredentialBinding | None,
    ) -> ResolvedCredential | None:
        if binding is None:
            return None
        if self._credential_provider is None:  # pragma: no cover - 前置组装检查已覆盖
            raise CredentialResolutionError("credential provider was not configured")
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
