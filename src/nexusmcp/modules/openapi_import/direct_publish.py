"""Imported Operation 的单事务 Direct Publish Use Case。"""

from dataclasses import dataclass
from datetime import datetime

from nexusmcp.modules.catalog.domain import ToolStatus, ToolVersionStatus, ToolVisibility
from nexusmcp.modules.catalog.publish import (
    PublishToolCommand,
    publish_tool_in_transaction,
)
from nexusmcp.modules.connectors.domain import ToolBindingStatus
from nexusmcp.modules.openapi_import.review import (
    ReviewImportedOperation,
    ReviewImportedOperationCommand,
    ReviewImportedOperationResult,
)
from nexusmcp.modules.openapi_import.review_ports import ReviewUnitOfWorkFactory
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import InvalidReviewStateError, InvalidToolStateError
from nexusmcp.shared.identifiers import IdentifierGenerator
from nexusmcp.shared.request_context import ActorContext


@dataclass(frozen=True, slots=True)
class DirectPublishImportedOperationCommand:
    context: ActorContext
    operation_id: str
    owner: str
    visibility: ToolVisibility = ToolVisibility.PUBLIC
    review_notes: str | None = None


@dataclass(frozen=True, slots=True)
class DirectPublishImportedOperationResult:
    operation_id: str
    tool_id: str
    tool_version_id: str
    tool_binding_id: str
    canonical_name: str
    version: int
    schema_digest: str
    binding_digest: str
    retired_tool_version_id: str | None
    published_at: datetime
    already_published: bool


class DirectPublishImportedOperation:
    def __init__(
        self,
        unit_of_work_factory: ReviewUnitOfWorkFactory,
        clock: Clock,
        identifier_generator: IdentifierGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._reviewer = ReviewImportedOperation(
            unit_of_work_factory,
            clock,
            identifier_generator,
        )

    async def execute(
        self,
        command: DirectPublishImportedOperationCommand,
    ) -> DirectPublishImportedOperationResult:
        published_at = self._clock.now()
        if published_at.tzinfo is None:
            raise ValueError("publish clock must return a timezone-aware datetime")
        tenant_id = command.context.tenant_id
        async with self._unit_of_work_factory() as unit_of_work:
            reviewed = await self._reviewer.execute_in_transaction(
                unit_of_work,
                ReviewImportedOperationCommand(
                    context=command.context,
                    operation_id=command.operation_id,
                    owner=command.owner,
                    visibility=command.visibility,
                    review_notes=command.review_notes,
                ),
            )
            version = await unit_of_work.catalog.get_version_for_update(
                tenant_id,
                reviewed.tool_version_id,
            )
            binding = await unit_of_work.bindings.get_by_tool_version_for_update(
                tenant_id,
                reviewed.tool_version_id,
            )
            tool = await unit_of_work.catalog.get_tool_for_update(
                tenant_id,
                reviewed.tool_id,
            )
            if version is None or binding is None or tool is None:
                raise InvalidReviewStateError("reviewed publication resources were incomplete")

            if version.status is ToolVersionStatus.PUBLISHED:
                if (
                    binding.status is not ToolBindingStatus.PUBLISHED
                    or tool.status is not ToolStatus.ACTIVE
                    or version.published_at is None
                ):
                    raise InvalidToolStateError(
                        "published operation resources were not in one consistent state"
                    )
                return _result(
                    reviewed,
                    retired_tool_version_id=None,
                    published_at=version.published_at,
                    already_published=True,
                )

            if version.status is ToolVersionStatus.DRAFT:
                version = version.submit_for_review(published_at)
                await unit_of_work.catalog.save_version(tenant_id, version)
            elif version.status is not ToolVersionStatus.REVIEW:
                raise InvalidToolStateError(
                    f"tool version {version.id} cannot be directly published from "
                    f"{version.status.value}"
                )

            publication = await publish_tool_in_transaction(
                unit_of_work,
                PublishToolCommand(
                    context=command.context,
                    tool_id=reviewed.tool_id,
                    tool_version_id=reviewed.tool_version_id,
                    expected_schema_digest=reviewed.schema_digest,
                    expected_binding_digest=reviewed.binding_digest,
                ),
                published_at=published_at,
            )
            await unit_of_work.commit()

        return _result(
            reviewed,
            retired_tool_version_id=publication.retired_tool_version_id,
            published_at=publication.event.occurred_at,
            already_published=False,
        )


def _result(
    reviewed: ReviewImportedOperationResult,
    *,
    retired_tool_version_id: str | None,
    published_at: datetime,
    already_published: bool,
) -> DirectPublishImportedOperationResult:
    return DirectPublishImportedOperationResult(
        operation_id=reviewed.operation_id,
        tool_id=reviewed.tool_id,
        tool_version_id=reviewed.tool_version_id,
        tool_binding_id=reviewed.tool_binding_id,
        canonical_name=reviewed.canonical_name,
        version=reviewed.version,
        schema_digest=reviewed.schema_digest,
        binding_digest=reviewed.binding_digest,
        retired_tool_version_id=retired_tool_version_id,
        published_at=published_at,
        already_published=already_published,
    )
