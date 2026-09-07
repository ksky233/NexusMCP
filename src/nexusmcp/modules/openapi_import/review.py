"""Accepted ImportedOperation 生成 Draft ToolVersion/Binding 的 Use Case。"""

from dataclasses import dataclass, replace
from typing import Any

from nexusmcp.modules.catalog.digests import calculate_schema_digest
from nexusmcp.modules.catalog.domain import (
    Tool,
    ToolSideEffect,
    ToolStatus,
    ToolVersion,
    ToolVersionStatus,
    ToolVisibility,
)
from nexusmcp.modules.connectors.digests import calculate_binding_digest
from nexusmcp.modules.connectors.domain import (
    ToolBinding,
    ToolBindingStatus,
    ToolBindingType,
)
from nexusmcp.modules.openapi_import.domain import (
    ImportedOperation,
    OperationConflictStatus,
    OperationReviewStatus,
)
from nexusmcp.modules.openapi_import.review_ports import (
    ReviewUnitOfWork,
    ReviewUnitOfWorkFactory,
)
from nexusmcp.modules.registry.domain import UpstreamStatus
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import (
    ImportedOperationNotFoundError,
    InvalidReviewStateError,
    TenantBoundaryViolationError,
    UpstreamNotActiveError,
)
from nexusmcp.shared.identifiers import IdentifierGenerator
from nexusmcp.shared.request_context import ActorContext


@dataclass(frozen=True, slots=True)
class ReviewImportedOperationCommand:
    context: ActorContext
    operation_id: str
    owner: str
    visibility: ToolVisibility = ToolVisibility.PUBLIC
    review_notes: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewImportedOperationResult:
    operation_id: str
    tool_id: str
    tool_version_id: str
    tool_binding_id: str
    canonical_name: str
    version: int
    schema_digest: str
    binding_digest: str


class ReviewImportedOperation:
    def __init__(
        self,
        unit_of_work_factory: ReviewUnitOfWorkFactory,
        clock: Clock,
        identifier_generator: IdentifierGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._identifier_generator = identifier_generator

    async def execute(
        self,
        command: ReviewImportedOperationCommand,
    ) -> ReviewImportedOperationResult:
        async with self._unit_of_work_factory() as unit_of_work:
            result = await self.execute_in_transaction(unit_of_work, command)
            await unit_of_work.commit()
            return result

    async def execute_in_transaction(
        self,
        unit_of_work: ReviewUnitOfWork,
        command: ReviewImportedOperationCommand,
    ) -> ReviewImportedOperationResult:
        """复用调用方事务完成 Review，不在内部 Commit。"""

        tenant_id = command.context.tenant_id
        operation = await unit_of_work.imports.get_operation_for_update(
            tenant_id,
            command.operation_id,
        )
        if operation is None:
            raise ImportedOperationNotFoundError(
                f"imported operation {command.operation_id} was not found in tenant"
            )
        if operation.review_status is OperationReviewStatus.ACCEPTED:
            return await self._existing_result(unit_of_work, tenant_id, operation)
        if operation.conflict_status is not OperationConflictStatus.NONE:
            raise InvalidReviewStateError(
                f"operation {operation.id} has conflict {operation.conflict_status.value}"
            )
        if operation.generated_tool_name is None:
            raise InvalidReviewStateError("operation has no generated tool name")

        upstream = await unit_of_work.upstreams.get_for_update(
            tenant_id,
            operation.upstream_service_id,
        )
        if upstream is None:
            raise TenantBoundaryViolationError(
                "operation upstream was not found in requested tenant"
            )
        if upstream.status is not UpstreamStatus.ACTIVE:
            raise UpstreamNotActiveError(f"upstream {upstream.id} is not active")

        tool = await unit_of_work.catalog.get_tool_by_name_for_update(
            tenant_id,
            operation.generated_tool_name,
        )
        if tool is None:
            tool = Tool(
                id=self._identifier_generator.new_id(),
                tenant_id=tenant_id,
                namespace=upstream.namespace,
                canonical_name=operation.generated_tool_name,
                owner=command.owner,
                status=ToolStatus.DISABLED,
            )
            await unit_of_work.catalog.add_tool(tenant_id, tool)

        version_number = await unit_of_work.catalog.next_version_number(
            tenant_id,
            tool.id,
        )
        version = self._build_version(command, operation, tool, version_number)
        binding = self._build_binding(operation, version)
        accepted_operation = operation.accept(
            draft_tool_version_id=version.id,
            draft_tool_binding_id=binding.id,
            review_notes=command.review_notes,
        )

        await unit_of_work.catalog.add_version(tenant_id, version)
        await unit_of_work.bindings.add(tenant_id, binding)
        await unit_of_work.imports.save_operation(tenant_id, accepted_operation)

        return ReviewImportedOperationResult(
            operation_id=operation.id,
            tool_id=tool.id,
            tool_version_id=version.id,
            tool_binding_id=binding.id,
            canonical_name=tool.canonical_name,
            version=version.version,
            schema_digest=version.schema_digest,
            binding_digest=binding.binding_digest,
        )

    def _build_version(
        self,
        command: ReviewImportedOperationCommand,
        operation: ImportedOperation,
        tool: Tool,
        version_number: int,
    ) -> ToolVersion:
        normalized = operation.normalized_operation
        input_schema = _mapping(normalized.get("tool_input_schema"), "tool input schema")
        raw_output_schema = normalized.get("tool_output_schema")
        output_schema = (
            _mapping(raw_output_schema, "tool output schema")
            if raw_output_schema is not None
            else None
        )
        side_effect_value = normalized.get("side_effect", "unknown")
        try:
            side_effect = ToolSideEffect(str(side_effect_value))
        except ValueError:
            side_effect = ToolSideEffect.UNKNOWN
        summary = _text(normalized.get("summary")) or operation.operation_id or tool.canonical_name
        description = _text(normalized.get("description")) or summary
        tags = tuple(_string_list(normalized.get("tags", ())))
        return ToolVersion(
            id=self._identifier_generator.new_id(),
            tenant_id=command.context.tenant_id,
            tool_id=tool.id,
            version=version_number,
            display_name=summary,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            schema_digest=calculate_schema_digest(input_schema, output_schema),
            tags=tags,
            side_effect=side_effect,
            visibility=command.visibility,
            status=ToolVersionStatus.DRAFT,
            created_by=command.context.principal_id,
            created_at=self._clock.now(),
        )

    def _build_binding(
        self,
        operation: ImportedOperation,
        version: ToolVersion,
    ) -> ToolBinding:
        normalized = operation.normalized_operation
        parameters = _list_of_mappings(normalized.get("parameters", ()), "parameters")
        request_body_value = normalized.get("request_body")
        request_body = (
            _mapping(request_body_value, "request body") if request_body_value is not None else None
        )
        binding_config = {
            "method": operation.method,
            "path_template": operation.path,
            "parameters": [
                {
                    "argument_name": parameter.get("argument_name"),
                    "upstream_name": parameter.get("upstream_name"),
                    "location": parameter.get("location"),
                    "required": parameter.get("required") is True,
                }
                for parameter in parameters
            ],
            "request_body": (
                {
                    "argument_name": request_body.get("argument_name"),
                    "content_type": request_body.get("content_type"),
                    "required": request_body.get("required") is True,
                }
                if request_body is not None
                else None
            ),
        }
        binding = ToolBinding(
            id=self._identifier_generator.new_id(),
            tenant_id=operation.tenant_id,
            tool_version_id=version.id,
            upstream_service_id=operation.upstream_service_id,
            imported_operation_id=operation.id,
            binding_type=ToolBindingType.HTTP,
            binding_config=binding_config,
            binding_digest="pending",
            status=ToolBindingStatus.DRAFT,
            created_at=self._clock.now(),
        )
        return replace(binding, binding_digest=calculate_binding_digest(binding))

    @staticmethod
    async def _existing_result(
        unit_of_work: ReviewUnitOfWork,
        tenant_id: str,
        operation: ImportedOperation,
    ) -> ReviewImportedOperationResult:
        if operation.draft_tool_version_id is None or operation.draft_tool_binding_id is None:
            raise InvalidReviewStateError("accepted operation is missing draft references")
        version = await unit_of_work.catalog.get_version_by_id(
            tenant_id,
            operation.draft_tool_version_id,
        )
        binding = await unit_of_work.bindings.get_by_id(
            tenant_id,
            operation.draft_tool_binding_id,
        )
        if version is None or binding is None:
            raise InvalidReviewStateError("accepted operation draft resources were not found")
        tool = await unit_of_work.catalog.get_tool_by_id(tenant_id, version.tool_id)
        if tool is None:
            raise InvalidReviewStateError("accepted operation tool was not found")
        return ReviewImportedOperationResult(
            operation_id=operation.id,
            tool_id=tool.id,
            tool_version_id=version.id,
            tool_binding_id=binding.id,
            canonical_name=tool.canonical_name,
            version=version.version,
            schema_digest=version.schema_digest,
            binding_digest=binding.binding_digest,
        )


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidReviewStateError(f"normalized {field_name} is invalid")
    return value


def _list_of_mappings(value: object, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise InvalidReviewStateError(f"normalized {field_name} is invalid")
    return value


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise InvalidReviewStateError("normalized tags are invalid")
    return list(value)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
