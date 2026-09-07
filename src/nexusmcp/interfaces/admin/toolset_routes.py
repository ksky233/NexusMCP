"""Toolset Aggregate 的 Admin HTTP Routes。"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from nexusmcp.interfaces.admin.query_models import PageMetadata
from nexusmcp.interfaces.admin.toolset_models import (
    ChangeToolsetStatusRequest,
    CreateToolsetRequest,
    ReplaceToolsetAccessGrantsRequest,
    ReplaceToolsetMembersRequest,
    ToolsetPageResponse,
    ToolsetResponse,
    UpdateToolsetRequest,
)
from nexusmcp.interfaces.http.errors import problem_responses
from nexusmcp.modules.toolsets.domain import (
    ToolsetDiscoveryMode,
    ToolsetKind,
    ToolsetStatus,
)
from nexusmcp.modules.toolsets.use_cases import (
    ActivateToolset,
    ChangeToolsetStatusCommand,
    CreateToolset,
    CreateToolsetCommand,
    DisableToolset,
    GetToolset,
    ListToolsets,
    ListToolsetsQuery,
    ReplaceToolsetGrants,
    ReplaceToolsetGrantsCommand,
    ReplaceToolsetMembers,
    ReplaceToolsetMembersCommand,
    UpdateToolset,
    UpdateToolsetCommand,
)
from nexusmcp.shared.request_context import ActorContext


@dataclass(frozen=True, slots=True)
class ToolsetAdminServices:
    create: CreateToolset
    list: ListToolsets
    get: GetToolset
    update: UpdateToolset
    replace_members: ReplaceToolsetMembers
    replace_grants: ReplaceToolsetGrants
    activate: ActivateToolset
    disable: DisableToolset


def _admin_context(request: Request) -> ActorContext:
    context: ActorContext = request.state.actor_context
    return context


AdminContext = Annotated[ActorContext, Depends(_admin_context)]


def create_toolset_router(services: ToolsetAdminServices) -> APIRouter:
    router = APIRouter(prefix="/toolsets", tags=["toolsets"])

    @router.post(
        "",
        response_model=ToolsetResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createToolset",
        responses=problem_responses(400, 409),
    )
    async def create_toolset(
        request: CreateToolsetRequest,
        context: AdminContext,
    ) -> ToolsetResponse:
        profile = await services.create.execute(
            CreateToolsetCommand(
                context=context,
                slug=request.slug,
                name=request.name,
                description=request.description,
                discovery_mode=request.discovery_mode,
            )
        )
        return ToolsetResponse.from_profile(profile)

    @router.get(
        "",
        response_model=ToolsetPageResponse,
        operation_id="listToolsets",
        responses=problem_responses(422),
    )
    async def list_toolsets(
        context: AdminContext,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        query_text: Annotated[str | None, Query(alias="q", min_length=1, max_length=128)] = None,
        toolset_status: Annotated[ToolsetStatus | None, Query(alias="status")] = None,
        kind: ToolsetKind | None = None,
        discovery_mode: ToolsetDiscoveryMode | None = None,
    ) -> ToolsetPageResponse:
        page = await services.list.execute(
            ListToolsetsQuery(
                context=context,
                offset=offset,
                limit=limit,
                text=query_text,
                status=toolset_status,
                kind=kind,
                discovery_mode=discovery_mode,
            )
        )
        return ToolsetPageResponse(
            items=[ToolsetResponse.from_profile(item) for item in page.items],
            page=PageMetadata(offset=page.offset, limit=page.limit, total=page.total),
        )

    @router.get(
        "/{toolset_id}",
        response_model=ToolsetResponse,
        operation_id="getToolset",
        responses=problem_responses(404),
    )
    async def get_toolset(toolset_id: str, context: AdminContext) -> ToolsetResponse:
        return ToolsetResponse.from_profile(await services.get.execute(context, toolset_id))

    @router.put(
        "/{toolset_id}",
        response_model=ToolsetResponse,
        operation_id="updateToolset",
        responses=problem_responses(400, 404, 409),
    )
    async def update_toolset(
        toolset_id: str,
        request: UpdateToolsetRequest,
        context: AdminContext,
    ) -> ToolsetResponse:
        return ToolsetResponse.from_profile(
            await services.update.execute(
                UpdateToolsetCommand(
                    context=context,
                    toolset_id=toolset_id,
                    expected_revision=request.expected_revision,
                    name=request.name,
                    description=request.description,
                    discovery_mode=request.discovery_mode,
                )
            )
        )

    @router.put(
        "/{toolset_id}/members",
        response_model=ToolsetResponse,
        operation_id="replaceToolsetMembers",
        responses=problem_responses(400, 404, 409, 422),
    )
    async def replace_toolset_members(
        toolset_id: str,
        request: ReplaceToolsetMembersRequest,
        context: AdminContext,
    ) -> ToolsetResponse:
        return ToolsetResponse.from_profile(
            await services.replace_members.execute(
                ReplaceToolsetMembersCommand(
                    context=context,
                    toolset_id=toolset_id,
                    expected_revision=request.expected_revision,
                    tool_ids=tuple(request.tool_ids),
                )
            )
        )

    @router.put(
        "/{toolset_id}/grants",
        response_model=ToolsetResponse,
        operation_id="replaceToolsetAccessGrants",
        responses=problem_responses(400, 404, 409),
    )
    async def replace_toolset_grants(
        toolset_id: str,
        request: ReplaceToolsetAccessGrantsRequest,
        context: AdminContext,
    ) -> ToolsetResponse:
        return ToolsetResponse.from_profile(
            await services.replace_grants.execute(
                ReplaceToolsetGrantsCommand(
                    context=context,
                    toolset_id=toolset_id,
                    expected_revision=request.expected_revision,
                    principal_ids=tuple(request.principal_ids),
                )
            )
        )

    @router.post(
        "/{toolset_id}/activate",
        response_model=ToolsetResponse,
        operation_id="activateToolset",
        responses=problem_responses(400, 404, 409),
    )
    async def activate_toolset(
        toolset_id: str,
        request: ChangeToolsetStatusRequest,
        context: AdminContext,
    ) -> ToolsetResponse:
        return ToolsetResponse.from_profile(
            await services.activate.execute(
                ChangeToolsetStatusCommand(
                    context=context,
                    toolset_id=toolset_id,
                    expected_revision=request.expected_revision,
                )
            )
        )

    @router.post(
        "/{toolset_id}/disable",
        response_model=ToolsetResponse,
        operation_id="disableToolset",
        responses=problem_responses(400, 404, 409),
    )
    async def disable_toolset(
        toolset_id: str,
        request: ChangeToolsetStatusRequest,
        context: AdminContext,
    ) -> ToolsetResponse:
        return ToolsetResponse.from_profile(
            await services.disable.execute(
                ChangeToolsetStatusCommand(
                    context=context,
                    toolset_id=toolset_id,
                    expected_revision=request.expected_revision,
                )
            )
        )

    return router
