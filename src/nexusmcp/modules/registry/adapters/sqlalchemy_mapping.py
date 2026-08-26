"""Upstream Domain 与 SQLAlchemy Model 之间的显式 Mapping。"""

from copy import deepcopy

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.modules.registry.domain import (
    UpstreamService,
    UpstreamServiceType,
    UpstreamStatus,
)


def upstream_to_model(upstream: UpstreamService) -> UpstreamServiceModel:
    return UpstreamServiceModel(
        id=as_uuid(upstream.id, field_name="upstream service id"),
        tenant_id=as_uuid(upstream.tenant_id, field_name="tenant id"),
        namespace=upstream.namespace,
        name=upstream.name,
        description=upstream.description,
        owner=upstream.owner,
        service_type=upstream.service_type.value,
        transport_type=upstream.transport_type,
        endpoint=upstream.endpoint,
        protocol_min=upstream.protocol_min,
        protocol_max=upstream.protocol_max,
        auth_scheme=upstream.auth_scheme,
        config_json=deepcopy(dict(upstream.config)),
        status=upstream.status.value,
    )


def update_upstream_model(model: UpstreamServiceModel, upstream: UpstreamService) -> None:
    model.description = upstream.description
    model.owner = upstream.owner
    model.endpoint = upstream.endpoint
    model.protocol_min = upstream.protocol_min
    model.protocol_max = upstream.protocol_max
    model.auth_scheme = upstream.auth_scheme
    model.config_json = deepcopy(dict(upstream.config))
    model.status = upstream.status.value


def upstream_from_model(model: UpstreamServiceModel) -> UpstreamService:
    return UpstreamService(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        namespace=model.namespace,
        name=model.name,
        description=model.description,
        owner=model.owner,
        service_type=UpstreamServiceType(model.service_type),
        transport_type=model.transport_type,
        endpoint=model.endpoint,
        protocol_min=model.protocol_min,
        protocol_max=model.protocol_max,
        auth_scheme=model.auth_scheme,
        config=deepcopy(model.config_json),
        status=UpstreamStatus(model.status),
    )
