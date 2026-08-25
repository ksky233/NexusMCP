"""Draft ToolVersion 提交 Review 的 Application Use Case。"""

from dataclasses import dataclass

from nexusmcp.modules.catalog.domain import ToolVersionStatus
from nexusmcp.modules.catalog.ports import CatalogUnitOfWorkFactory
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import InvalidToolStateError, ToolVersionNotFoundError
from nexusmcp.shared.request_context import RequestContext


@dataclass(frozen=True, slots=True)
class SubmitToolVersionForReviewCommand:
    context: RequestContext
    tool_version_id: str


class SubmitToolVersionForReview:
    def __init__(self, unit_of_work_factory: CatalogUnitOfWorkFactory, clock: Clock) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    async def execute(self, command: SubmitToolVersionForReviewCommand) -> None:
        tenant_id = command.context.tenant_id
        async with self._unit_of_work_factory() as unit_of_work:
            version = await unit_of_work.catalog.get_version_for_update(
                tenant_id,
                command.tool_version_id,
            )
            if version is None:
                raise ToolVersionNotFoundError(
                    f"tool version {command.tool_version_id} was not found in tenant"
                )
            if version.status is not ToolVersionStatus.DRAFT:
                raise InvalidToolStateError(
                    f"tool version {version.id} must be draft before review"
                )
            await unit_of_work.catalog.save_version(
                tenant_id,
                version.submit_for_review(self._clock.now()),
            )
            await unit_of_work.commit()
