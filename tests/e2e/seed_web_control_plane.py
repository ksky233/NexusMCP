"""为 disposable Web E2E Database 创建空 Tenant 基线。"""

import asyncio
import os
import uuid

from sqlalchemy import insert, text
from sqlalchemy.engine import make_url

from nexusmcp.infrastructure.persistence.engine import create_engine
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel

TENANT_ID = "00000000-0000-0000-0000-00000000000a"
BUSINESS_TABLES = """
    toolset_access_grant,
    toolset_member,
    toolset,
    tool_search_reindex_job,
    tool_search_embedding,
    audit_event,
    execution_attempt,
    tool_execution,
    approval_request,
    tool_binding,
    imported_operation,
    openapi_import_job,
    tool_version,
    tool,
    upstream_service,
    tenant
"""


async def seed() -> None:
    database_url = os.environ.get("NEXUSMCP_TEST_DATABASE_URL")
    if not database_url:
        raise RuntimeError("NEXUSMCP_TEST_DATABASE_URL is required")
    parsed = make_url(database_url)
    if "test" not in (parsed.database or "").lower():
        raise RuntimeError("Web E2E database name must contain test")
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"TRUNCATE TABLE {BUSINESS_TABLES} CASCADE"))
            await connection.execute(
                insert(TenantModel).values(
                    id=uuid.UUID(TENANT_ID),
                    name="Web E2E Tenant",
                    status="active",
                )
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
