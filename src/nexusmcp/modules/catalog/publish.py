"""ToolVersion 与 ToolBinding 原子发布的 Application Use Case。"""

from dataclasses import dataclass
from datetime import datetime

from nexusmcp.modules.catalog.digests import calculate_schema_digest
from nexusmcp.modules.catalog.domain import Tool, ToolVersion, ToolVersionStatus
from nexusmcp.modules.catalog.events import ToolPublished
from nexusmcp.modules.catalog.ports import CatalogUnitOfWork, CatalogUnitOfWorkFactory
from nexusmcp.modules.connectors.digests import calculate_binding_digest
from nexusmcp.modules.connectors.domain import ToolBinding, ToolBindingStatus
from nexusmcp.modules.registry.domain import UpstreamService, UpstreamStatus
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import (
    BindingDigestMismatchError,
    InvalidToolStateError,
    PublishConflictError,
    SchemaDigestMismatchError,
    TenantBoundaryViolationError,
    ToolBindingNotFoundError,
    ToolNotFoundError,
    ToolVersionNotFoundError,
    UpstreamNotActiveError,
)
from nexusmcp.shared.request_context import ActorContext


@dataclass(frozen=True, slots=True)
class PublishToolCommand:
    context: ActorContext
    tool_id: str
    tool_version_id: str
    expected_schema_digest: str
    expected_binding_digest: str


@dataclass(frozen=True, slots=True)
class PublishToolResult:
    event: ToolPublished
    retired_tool_version_id: str | None


class PublishTool:
    def __init__(self, unit_of_work_factory: CatalogUnitOfWorkFactory, clock: Clock) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    async def execute(self, command: PublishToolCommand) -> PublishToolResult:
        """验证发布快照，并在一个短事务内切换 Version/Binding。"""

        published_at = self._clock.now()
        if published_at.tzinfo is None:
            raise ValueError("publish clock must return a timezone-aware datetime")
        tenant_id = command.context.tenant_id
        async with self._unit_of_work_factory() as unit_of_work:
            tool = await unit_of_work.catalog.get_tool_for_update(tenant_id, command.tool_id)
            if tool is None:
                raise ToolNotFoundError(f"tool {command.tool_id} was not found in tenant")

            version = await unit_of_work.catalog.get_version_for_update(
                tenant_id,
                command.tool_version_id,
            )
            if version is None:
                raise ToolVersionNotFoundError(
                    f"tool version {command.tool_version_id} was not found in tenant"
                )

            binding = await unit_of_work.bindings.get_by_tool_version_for_update(
                tenant_id,
                version.id,
            )
            if binding is None:
                raise ToolBindingNotFoundError(
                    f"binding for tool version {version.id} was not found in tenant"
                )

            upstream = await unit_of_work.upstreams.get_for_update(
                tenant_id,
                binding.upstream_service_id,
            )
            if upstream is None:
                raise TenantBoundaryViolationError(
                    "binding upstream was not found in the requested tenant"
                )

            self._validate_publish_snapshot(command, tool, version, binding, upstream)
            retired_version_id = await self._retire_current_version(
                unit_of_work,
                tenant_id,
                tool,
                version,
                published_at,
            )

            await unit_of_work.catalog.save_version(
                tenant_id,
                version.publish(published_at),
            )
            await unit_of_work.bindings.save(
                tenant_id,
                binding.publish(published_at),
            )
            await unit_of_work.catalog.save_tool(tenant_id, tool.activate())
            await unit_of_work.commit()

        event = ToolPublished(
            tenant_id=tenant_id,
            tool_id=tool.id,
            tool_version_id=version.id,
            tool_binding_id=binding.id,
            canonical_name=tool.canonical_name,
            version=version.version,
            actor_id=command.context.principal_id,
            request_id=command.context.request_id,
            trace_id=command.context.trace_id,
            occurred_at=published_at,
        )
        return PublishToolResult(
            event=event,
            retired_tool_version_id=retired_version_id,
        )

    @staticmethod
    def _validate_publish_snapshot(
        command: PublishToolCommand,
        tool: Tool,
        version: ToolVersion,
        binding: ToolBinding,
        upstream: UpstreamService,
    ) -> None:
        tenant_ids = {
            tool.tenant_id,
            version.tenant_id,
            binding.tenant_id,
            upstream.tenant_id,
        }
        if tenant_ids != {command.context.tenant_id}:
            raise TenantBoundaryViolationError("publish aggregate crossed tenant boundary")
        if version.tool_id != tool.id or binding.tool_version_id != version.id:
            raise InvalidToolStateError("publish aggregate references do not match")
        if version.status is not ToolVersionStatus.REVIEW:
            raise InvalidToolStateError(f"tool version {version.id} must be review before publish")
        if binding.status is not ToolBindingStatus.DRAFT:
            raise InvalidToolStateError(f"tool binding {binding.id} must be draft before publish")
        if upstream.status is not UpstreamStatus.ACTIVE:
            raise UpstreamNotActiveError(f"upstream {upstream.id} is not active")

        calculated_schema_digest = calculate_schema_digest(
            version.input_schema,
            version.output_schema,
        )
        if (
            calculated_schema_digest != version.schema_digest
            or command.expected_schema_digest != version.schema_digest
        ):
            raise SchemaDigestMismatchError(f"tool version {version.id} schema digest changed")

        calculated_binding_digest = calculate_binding_digest(binding)
        if (
            calculated_binding_digest != binding.binding_digest
            or command.expected_binding_digest != binding.binding_digest
        ):
            raise BindingDigestMismatchError(f"tool binding {binding.id} digest changed")

    @staticmethod
    async def _retire_current_version(
        unit_of_work: CatalogUnitOfWork,
        tenant_id: str,
        tool: Tool,
        target_version: ToolVersion,
        retired_at: datetime,
    ) -> str | None:
        current = await unit_of_work.catalog.get_published_version(tenant_id, tool.id)
        if current is None:
            return None
        if current.version >= target_version.version:
            raise PublishConflictError(
                "target version must be newer than the current published version"
            )

        locked_current = await unit_of_work.catalog.get_version_for_update(
            tenant_id,
            current.id,
        )
        if locked_current is None or locked_current.status is not ToolVersionStatus.PUBLISHED:
            raise PublishConflictError("current published version changed during publish")
        current_binding = await unit_of_work.bindings.get_by_tool_version_for_update(
            tenant_id,
            locked_current.id,
        )
        if current_binding is None:
            raise ToolBindingNotFoundError(
                f"published binding for version {locked_current.id} was not found"
            )
        if current_binding.status is not ToolBindingStatus.PUBLISHED:
            raise InvalidToolStateError("current published version binding is not published")

        # 先释放 Partial Unique Index，再发布新 Version；所有 Flush 仍在同一事务中。
        await unit_of_work.catalog.save_version(
            tenant_id,
            locked_current.retire(retired_at),
        )
        await unit_of_work.bindings.save(tenant_id, current_binding.disable())
        return locked_current.id
