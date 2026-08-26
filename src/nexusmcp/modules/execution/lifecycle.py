"""Execution 计划、终态与 Audit 的短事务编排。"""

from dataclasses import dataclass
from datetime import datetime

from nexusmcp.modules.approval.use_cases import (
    ConsumeApprovalCommand,
    consume_locked_approval,
)
from nexusmcp.modules.audit.domain import AuditAction, AuditEvent, AuditOutcome
from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.execution.domain import (
    ExecutionErrorCategory,
    ExecutionStatus,
    ToolExecution,
)
from nexusmcp.modules.execution.ports import ExecutionUnitOfWorkFactory
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import (
    ApprovalExpiredError,
    InvalidExecutionStateError,
    ToolExecutionNotFoundError,
)
from nexusmcp.shared.identifiers import IdentifierGenerator
from nexusmcp.shared.request_context import ActorContext


@dataclass(frozen=True, slots=True)
class PlanExecutionCommand:
    context: ActorContext
    principal_id: str
    tool_id: str
    tool_version_id: str
    tool_binding_id: str
    arguments_digest: str
    policy_version: str
    policy_reason_code: str
    side_effect: ToolSideEffect
    approval_id: str | None = None
    credential_binding_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class RecordCallDecisionCommand:
    context: ActorContext
    principal_id: str
    tool_version_id: str
    arguments_digest: str
    policy_version: str
    reason_code: str
    outcome: AuditOutcome


class ExecutionLifecycle:
    def __init__(
        self,
        unit_of_work_factory: ExecutionUnitOfWorkFactory,
        clock: Clock,
        identifier_generator: IdentifierGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._identifier_generator = identifier_generator

    async def plan(self, command: PlanExecutionCommand) -> ToolExecution:
        now = self._clock.now()
        execution = ToolExecution(
            id=self._identifier_generator.new_id(),
            tenant_id=command.context.tenant_id,
            request_id=command.context.request_id,
            trace_id=command.context.trace_id,
            principal_id=command.principal_id,
            tool_id=command.tool_id,
            tool_version_id=command.tool_version_id,
            tool_binding_id=command.tool_binding_id,
            approval_id=command.approval_id,
            credential_binding_id=command.credential_binding_id,
            arguments_digest=command.arguments_digest,
            policy_version=command.policy_version,
            policy_reason_code=command.policy_reason_code,
            side_effect=command.side_effect,
            status=ExecutionStatus.PLANNED,
            planned_at=now,
            idempotency_key=command.idempotency_key,
        ).start(now)
        async with self._unit_of_work_factory() as unit_of_work:
            if command.approval_id is not None:
                consume_command = ConsumeApprovalCommand(
                    context=command.context,
                    approval_id=command.approval_id,
                    principal_id=command.principal_id,
                    tool_version_id=command.tool_version_id,
                    arguments_digest=command.arguments_digest,
                    policy_version=command.policy_version,
                )
                try:
                    await consume_locked_approval(
                        unit_of_work.approvals,
                        consume_command,
                        now,
                    )
                except ApprovalExpiredError:
                    await unit_of_work.commit()
                    raise
            await unit_of_work.executions.add(command.context.tenant_id, execution)
            await unit_of_work.audits.append(
                self._execution_audit(execution, AuditOutcome.ALLOWED, now)
            )
            await unit_of_work.commit()
        return execution

    async def record_call_decision(self, command: RecordCallDecisionCommand) -> None:
        event = AuditEvent(
            id=self._identifier_generator.new_id(),
            tenant_id=command.context.tenant_id,
            actor_id=command.principal_id,
            action=AuditAction.TOOL_CALL,
            resource_type="tool_version",
            resource_id=command.tool_version_id,
            outcome=command.outcome,
            request_id=command.context.request_id,
            trace_id=command.context.trace_id,
            occurred_at=self._clock.now(),
            arguments_digest=command.arguments_digest,
            policy_version=command.policy_version,
            reason_code=command.reason_code,
        )
        async with self._unit_of_work_factory() as unit_of_work:
            await unit_of_work.audits.append(event)
            await unit_of_work.commit()

    async def succeed(self, tenant_id: str, execution_id: str) -> ToolExecution:
        return await self._finish(
            tenant_id,
            execution_id,
            status=ExecutionStatus.SUCCEEDED,
        )

    async def fail(
        self,
        tenant_id: str,
        execution_id: str,
        *,
        error_code: str,
        category: ExecutionErrorCategory,
        outcome_unknown: bool = False,
    ) -> ToolExecution:
        return await self._finish(
            tenant_id,
            execution_id,
            status=ExecutionStatus.UNKNOWN if outcome_unknown else ExecutionStatus.FAILED,
            error_code=error_code,
            category=category,
        )

    async def cancel(self, tenant_id: str, execution_id: str) -> ToolExecution:
        return await self._finish(
            tenant_id,
            execution_id,
            status=ExecutionStatus.CANCELLED,
        )

    async def _finish(
        self,
        tenant_id: str,
        execution_id: str,
        *,
        status: ExecutionStatus,
        error_code: str | None = None,
        category: ExecutionErrorCategory | None = None,
    ) -> ToolExecution:
        now = self._clock.now()
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await unit_of_work.executions.get_for_update(tenant_id, execution_id)
            if execution is None:
                raise ToolExecutionNotFoundError("execution did not exist in tenant")
            if execution.status is not ExecutionStatus.RUNNING:
                raise InvalidExecutionStateError(f"execution was already {execution.status.value}")
            if status is ExecutionStatus.SUCCEEDED:
                terminal = execution.succeed(now)
                outcome = AuditOutcome.SUCCEEDED
            elif status is ExecutionStatus.UNKNOWN:
                if error_code is None:
                    raise ValueError("unknown execution requires error code")
                terminal = execution.mark_unknown(error_code=error_code, finished_at=now)
                outcome = AuditOutcome.UNKNOWN
            elif status is ExecutionStatus.CANCELLED:
                terminal = execution.cancel(now)
                outcome = AuditOutcome.CANCELLED
            else:
                if error_code is None or category is None:
                    raise ValueError("failed execution requires error code and category")
                terminal = execution.fail(
                    error_code=error_code,
                    category=category,
                    finished_at=now,
                )
                outcome = AuditOutcome.FAILED
            await unit_of_work.executions.save(tenant_id, terminal)
            await unit_of_work.audits.append(self._execution_audit(terminal, outcome, now))
            await unit_of_work.commit()
        return terminal

    def _execution_audit(
        self,
        execution: ToolExecution,
        outcome: AuditOutcome,
        occurred_at: datetime,
    ) -> AuditEvent:
        return AuditEvent(
            id=self._identifier_generator.new_id(),
            tenant_id=execution.tenant_id,
            actor_id=execution.principal_id,
            action=AuditAction.TOOL_CALL,
            resource_type="tool_version",
            resource_id=execution.tool_version_id,
            outcome=outcome,
            request_id=execution.request_id,
            trace_id=execution.trace_id,
            occurred_at=occurred_at,
            arguments_digest=execution.arguments_digest,
            policy_version=execution.policy_version,
            reason_code=(
                execution.error_code
                if outcome in {AuditOutcome.FAILED, AuditOutcome.UNKNOWN, AuditOutcome.CANCELLED}
                else execution.policy_reason_code
            ),
            execution_id=execution.id,
            metadata={
                "side_effect": execution.side_effect.value,
                "execution_status": execution.status.value,
            },
        )
