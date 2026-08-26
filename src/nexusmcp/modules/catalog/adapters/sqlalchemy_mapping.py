"""Catalog Domain 与 SQLAlchemy Model 之间的显式 Mapping。"""

from copy import deepcopy

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.catalog.domain import (
    PublishedTool,
    Tool,
    ToolSideEffect,
    ToolStatus,
    ToolVersion,
    ToolVersionStatus,
    ToolVisibility,
)


def tool_to_model(tool: Tool) -> ToolModel:
    return ToolModel(
        id=as_uuid(tool.id, field_name="tool id"),
        tenant_id=as_uuid(tool.tenant_id, field_name="tenant id"),
        namespace=tool.namespace,
        canonical_name=tool.canonical_name,
        owner=tool.owner,
        status=tool.status.value,
    )


def update_tool_model(model: ToolModel, tool: Tool) -> None:
    """只更新稳定 Identity 允许变化的业务字段，不改写主键与 Tenant。"""

    model.namespace = tool.namespace
    model.canonical_name = tool.canonical_name
    model.owner = tool.owner
    model.status = tool.status.value


def tool_from_model(model: ToolModel) -> Tool:
    return Tool(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        namespace=model.namespace,
        canonical_name=model.canonical_name,
        owner=model.owner,
        status=ToolStatus(model.status),
    )


def tool_version_to_model(
    version: ToolVersion,
    *,
    namespace: str = "",
    canonical_name: str = "",
) -> ToolVersionModel:
    search_name, search_tags, search_description = tool_version_search_fields(
        version,
        namespace=namespace,
        canonical_name=canonical_name,
    )
    return ToolVersionModel(
        id=as_uuid(version.id, field_name="tool version id"),
        tenant_id=as_uuid(version.tenant_id, field_name="tenant id"),
        tool_id=as_uuid(version.tool_id, field_name="tool id"),
        version=version.version,
        display_name=version.display_name,
        description=version.description,
        input_schema_json=deepcopy(dict(version.input_schema)),
        output_schema_json=(
            deepcopy(dict(version.output_schema)) if version.output_schema is not None else None
        ),
        schema_digest=version.schema_digest,
        tags_json=list(version.tags),
        search_name=search_name,
        search_tags=search_tags,
        search_description=search_description,
        side_effect=version.side_effect.value,
        visibility=version.visibility.value,
        status=version.status.value,
        created_by=version.created_by,
        created_at=version.created_at,
        reviewed_at=version.reviewed_at,
        published_at=version.published_at,
        retired_at=version.retired_at,
    )


def update_tool_version_model(
    model: ToolVersionModel,
    version: ToolVersion,
    *,
    namespace: str = "",
    canonical_name: str = "",
) -> None:
    """保存 Domain 已验证的版本状态；发布后内容不可变由 Use Case/Domain 保证。"""

    model.version = version.version
    model.display_name = version.display_name
    model.description = version.description
    model.input_schema_json = deepcopy(dict(version.input_schema))
    model.output_schema_json = (
        deepcopy(dict(version.output_schema)) if version.output_schema is not None else None
    )
    model.schema_digest = version.schema_digest
    model.tags_json = list(version.tags)
    (
        model.search_name,
        model.search_tags,
        model.search_description,
    ) = tool_version_search_fields(
        version,
        namespace=namespace,
        canonical_name=canonical_name,
    )
    model.side_effect = version.side_effect.value
    model.visibility = version.visibility.value
    model.status = version.status.value
    model.created_by = version.created_by
    model.created_at = version.created_at
    model.reviewed_at = version.reviewed_at
    model.published_at = version.published_at
    model.retired_at = version.retired_at


def tool_version_from_model(model: ToolVersionModel) -> ToolVersion:
    return ToolVersion(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        tool_id=str(model.tool_id),
        version=model.version,
        display_name=model.display_name,
        description=model.description,
        input_schema=deepcopy(model.input_schema_json),
        output_schema=deepcopy(model.output_schema_json),
        schema_digest=model.schema_digest,
        tags=tuple(model.tags_json),
        side_effect=ToolSideEffect(model.side_effect),
        visibility=ToolVisibility(model.visibility),
        status=ToolVersionStatus(model.status),
        created_by=model.created_by,
        created_at=model.created_at,
        reviewed_at=model.reviewed_at,
        published_at=model.published_at,
        retired_at=model.retired_at,
    )


def published_tool_from_models(tool: ToolModel, version: ToolVersionModel) -> PublishedTool:
    return PublishedTool(
        tool_id=str(tool.id),
        tool_version_id=str(version.id),
        tenant_id=str(tool.tenant_id),
        canonical_name=tool.canonical_name,
        display_name=version.display_name,
        description=version.description,
        input_schema=deepcopy(version.input_schema_json),
        output_schema=deepcopy(version.output_schema_json),
        version=version.version,
        visibility=ToolVisibility(version.visibility),
        side_effect=ToolSideEffect(version.side_effect),
        schema_digest=version.schema_digest,
    )


def tool_version_search_fields(
    version: ToolVersion,
    *,
    namespace: str,
    canonical_name: str,
) -> tuple[str, str, str]:
    """构建 Version Search Snapshot；Domain 不感知 PostgreSQL FTS 字段。"""

    search_name = " ".join(
        part for part in (namespace, canonical_name, version.display_name) if part
    )
    return search_name, " ".join(version.tags), version.description
