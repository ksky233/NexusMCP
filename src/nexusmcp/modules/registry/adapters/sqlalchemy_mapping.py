"""Upstream Domain 与 SQLAlchemy Model 之间的显式 Mapping。"""

from copy import deepcopy

from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.modules.registry.domain import (
    UpstreamService,
    UpstreamServiceType,
    UpstreamStatus,
)


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
