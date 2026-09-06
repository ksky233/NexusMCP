"""Toolset Aggregate 与 SQLAlchemy Row 的显式 Mapping。"""

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.toolsets.adapters.sqlalchemy_models import (
    ToolsetAccessGrantModel,
    ToolsetMemberModel,
    ToolsetModel,
)
from nexusmcp.modules.toolsets.domain import (
    Toolset,
    ToolsetAccessGrant,
    ToolsetDiscoveryMode,
    ToolsetKind,
    ToolsetMember,
    ToolsetStatus,
)


def toolset_to_model(toolset: Toolset) -> ToolsetModel:
    return ToolsetModel(
        id=as_uuid(toolset.id, field_name="toolset id"),
        tenant_id=as_uuid(toolset.tenant_id, field_name="tenant id"),
        slug=toolset.slug,
        name=toolset.name,
        description=toolset.description,
        kind=toolset.kind.value,
        discovery_mode=toolset.discovery_mode.value,
        status=toolset.status.value,
        revision=toolset.revision,
        membership_digest=toolset.membership_digest,
        created_by=toolset.created_by,
        created_at=toolset.created_at,
        updated_at=toolset.updated_at,
    )


def update_toolset_model(model: ToolsetModel, toolset: Toolset) -> None:
    if (
        str(model.id) != toolset.id
        or str(model.tenant_id) != toolset.tenant_id
        or model.slug != toolset.slug
        or model.kind != toolset.kind.value
        or model.created_by != toolset.created_by
        or model.created_at != toolset.created_at
    ):
        raise ValueError("toolset stable identity fields are immutable")
    model.name = toolset.name
    model.description = toolset.description
    model.discovery_mode = toolset.discovery_mode.value
    model.status = toolset.status.value
    model.revision = toolset.revision
    model.membership_digest = toolset.membership_digest
    model.updated_at = toolset.updated_at


def member_to_model(member: ToolsetMember) -> ToolsetMemberModel:
    return ToolsetMemberModel(
        tenant_id=as_uuid(member.tenant_id, field_name="tenant id"),
        toolset_id=as_uuid(member.toolset_id, field_name="toolset id"),
        tool_id=as_uuid(member.tool_id, field_name="tool id"),
        added_by=member.added_by,
        added_at=member.added_at,
    )


def grant_to_model(grant: ToolsetAccessGrant) -> ToolsetAccessGrantModel:
    return ToolsetAccessGrantModel(
        tenant_id=as_uuid(grant.tenant_id, field_name="tenant id"),
        toolset_id=as_uuid(grant.toolset_id, field_name="toolset id"),
        principal_id=grant.principal_id,
        granted_by=grant.granted_by,
        granted_at=grant.granted_at,
    )


def toolset_from_models(
    model: ToolsetModel,
    members: tuple[ToolsetMemberModel, ...],
    grants: tuple[ToolsetAccessGrantModel, ...],
) -> Toolset:
    return Toolset(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        slug=model.slug,
        name=model.name,
        description=model.description,
        kind=ToolsetKind(model.kind),
        discovery_mode=ToolsetDiscoveryMode(model.discovery_mode),
        status=ToolsetStatus(model.status),
        revision=model.revision,
        membership_digest=model.membership_digest,
        created_by=model.created_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
        members=tuple(
            ToolsetMember(
                tenant_id=str(member.tenant_id),
                toolset_id=str(member.toolset_id),
                tool_id=str(member.tool_id),
                added_by=member.added_by,
                added_at=member.added_at,
            )
            for member in members
        ),
        grants=tuple(
            ToolsetAccessGrant(
                tenant_id=str(grant.tenant_id),
                toolset_id=str(grant.toolset_id),
                principal_id=grant.principal_id,
                granted_by=grant.granted_by,
                granted_at=grant.granted_at,
            )
            for grant in grants
        ),
    )
