"""ToolBinding Domain 与 SQLAlchemy Model 之间的显式 Mapping。"""

from copy import deepcopy

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.connectors.adapters.sqlalchemy_models import ToolBindingModel
from nexusmcp.modules.connectors.domain import (
    ToolBinding,
    ToolBindingStatus,
    ToolBindingType,
)


def tool_binding_to_model(binding: ToolBinding) -> ToolBindingModel:
    return ToolBindingModel(
        id=as_uuid(binding.id, field_name="tool binding id"),
        tenant_id=as_uuid(binding.tenant_id, field_name="tenant id"),
        tool_version_id=as_uuid(binding.tool_version_id, field_name="tool version id"),
        upstream_service_id=as_uuid(
            binding.upstream_service_id,
            field_name="upstream service id",
        ),
        imported_operation_id=(
            as_uuid(binding.imported_operation_id, field_name="imported operation id")
            if binding.imported_operation_id is not None
            else None
        ),
        binding_type=binding.binding_type.value,
        binding_config_json=deepcopy(dict(binding.binding_config)),
        binding_digest=binding.binding_digest,
        status=binding.status.value,
        created_at=binding.created_at,
        published_at=binding.published_at,
    )


def update_tool_binding_model(model: ToolBindingModel, binding: ToolBinding) -> None:
    """保留 Binding Identity，只更新 Domain 已批准的配置与生命周期字段。"""

    model.tool_version_id = as_uuid(binding.tool_version_id, field_name="tool version id")
    model.upstream_service_id = as_uuid(
        binding.upstream_service_id,
        field_name="upstream service id",
    )
    model.imported_operation_id = (
        as_uuid(binding.imported_operation_id, field_name="imported operation id")
        if binding.imported_operation_id is not None
        else None
    )
    model.binding_type = binding.binding_type.value
    model.binding_config_json = deepcopy(dict(binding.binding_config))
    model.binding_digest = binding.binding_digest
    model.status = binding.status.value
    model.created_at = binding.created_at
    model.published_at = binding.published_at


def tool_binding_from_model(model: ToolBindingModel) -> ToolBinding:
    return ToolBinding(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        tool_version_id=str(model.tool_version_id),
        upstream_service_id=str(model.upstream_service_id),
        imported_operation_id=(
            str(model.imported_operation_id) if model.imported_operation_id is not None else None
        ),
        binding_type=ToolBindingType(model.binding_type),
        binding_config=deepcopy(model.binding_config_json),
        binding_digest=model.binding_digest,
        status=ToolBindingStatus(model.status),
        created_at=model.created_at,
        published_at=model.published_at,
    )
