"""真实 PostgreSQL Baseline Migration 与核心约束测试。"""

import asyncio
import uuid

import pytest
from alembic import command
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from nexusmcp.infrastructure.persistence.engine import create_engine, create_session_factory
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from tests.integration.persistence.database import alembic_config, require_test_database_url

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "tenant",
    "upstream_service",
    "openapi_import_job",
    "imported_operation",
    "tool",
    "tool_version",
    "tool_binding",
}


async def table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
            return set(names)
    finally:
        await engine.dispose()


async def verify_jsonb_and_published_version_constraint(database_url: str) -> None:
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    tenant_id = uuid.uuid4()
    tool_id = uuid.uuid4()
    upstream_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:8]

    try:
        async with session_factory() as session:
            session.add(
                TenantModel(
                    id=tenant_id,
                    name=f"Integration Tenant {suffix}",
                    status="active",
                )
            )
            # 不依赖 ORM Relationship 推断顺序，显式落下 Aggregate Root 的 FK 前置记录。
            await session.flush()

            session.add(
                ToolModel(
                    id=tool_id,
                    tenant_id=tenant_id,
                    namespace="directory",
                    canonical_name=f"directory.get_employee_{suffix}",
                    owner="integration-test",
                    status="active",
                )
            )
            session.add(
                UpstreamServiceModel(
                    id=upstream_id,
                    tenant_id=tenant_id,
                    namespace="directory",
                    name=f"employee-directory-{suffix}",
                    description="Integration test upstream",
                    owner="integration-test",
                    service_type="http",
                    transport_type="http",
                    endpoint="http://127.0.0.1:9001",
                    auth_scheme="none",
                    config_json={"environment": "test", "features": ["openapi"]},
                    status="active",
                )
            )
            await session.flush()

            session.add(
                ToolVersionModel(
                    tenant_id=tenant_id,
                    tool_id=tool_id,
                    version=1,
                    display_name="Get employee",
                    description="Get one employee",
                    input_schema_json={
                        "type": "object",
                        "properties": {"employee_id": {"type": "string"}},
                        "required": ["employee_id"],
                    },
                    output_schema_json=None,
                    schema_digest="1" * 64,
                    tags_json=["directory", "read"],
                    side_effect="read_only",
                    visibility="public",
                    status="published",
                    created_by="integration-test",
                )
            )
            await session.commit()

        async with session_factory() as session:
            upstream = await session.get(UpstreamServiceModel, upstream_id)
            assert upstream is not None
            assert upstream.config_json == {
                "environment": "test",
                "features": ["openapi"],
            }

            published = await session.scalar(
                select(ToolVersionModel).where(
                    ToolVersionModel.tool_id == tool_id,
                    ToolVersionModel.status == "published",
                )
            )
            assert published is not None
            assert published.input_schema_json["required"] == ["employee_id"]

            session.add(
                ToolVersionModel(
                    tenant_id=tenant_id,
                    tool_id=tool_id,
                    version=2,
                    display_name="Get employee v2",
                    description="Conflicting published version",
                    input_schema_json={"type": "object", "properties": {}},
                    output_schema_json=None,
                    schema_digest="2" * 64,
                    tags_json=[],
                    side_effect="read_only",
                    visibility="public",
                    status="published",
                    created_by="integration-test",
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
    finally:
        await engine.dispose()


def test_postgresql_baseline_upgrade_constraints_and_downgrade() -> None:
    database_url = require_test_database_url()
    config = alembic_config(database_url)

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    assert EXPECTED_TABLES.issubset(asyncio.run(table_names(database_url)))

    asyncio.run(verify_jsonb_and_published_version_constraint(database_url))

    command.downgrade(config, "base")
    assert EXPECTED_TABLES.isdisjoint(asyncio.run(table_names(database_url)))

    # 为后续本地调试和其他 Integration Test 保持 Head 状态。
    command.upgrade(config, "head")
