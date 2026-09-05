"""仅供本地开发 Control Plane 使用的幂等 Tenant Bootstrap。"""

from sqlalchemy.dialects.postgresql import insert

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntimePort
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel


async def ensure_local_development_tenant(
    database_runtime: DatabaseRuntimePort,
    tenant_id: str,
) -> None:
    await ensure_configured_tenant(
        database_runtime,
        tenant_id,
        name="Local Development Tenant",
    )


async def ensure_configured_tenant(
    database_runtime: DatabaseRuntimePort,
    tenant_id: str,
    *,
    name: str,
) -> None:
    """为显式配置的单 Tenant 部署创建幂等基础事实。"""

    session_factory = database_runtime.require_session_factory()
    async with session_factory() as session:
        statement = (
            insert(TenantModel)
            .values(
                id=as_uuid(tenant_id, field_name="local tenant id"),
                name=name,
                status="active",
            )
            .on_conflict_do_nothing(index_elements=[TenantModel.id])
        )
        await session.execute(statement)
        await session.commit()
