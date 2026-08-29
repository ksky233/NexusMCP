"""Tool Search Reindex Job 的 PostgreSQL Store Adapter。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntimePort
from nexusmcp.modules.tool_search.adapters.sqlalchemy_models import (
    ToolSearchReindexJobModel,
)
from nexusmcp.modules.tool_search.index_management import (
    ToolSearchReindexJob,
    ToolSearchReindexJobStatus,
)
from nexusmcp.modules.tool_search.reindex_tools import ReindexToolsResult
from nexusmcp.shared.errors import ToolSearchReindexJobConflictError


class SqlAlchemyToolSearchReindexJobStore:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    async def create(self, job: ToolSearchReindexJob) -> None:
        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session:
            session.add(
                ToolSearchReindexJobModel(
                    id=as_uuid(job.id, field_name="reindex job id"),
                    tenant_id=as_uuid(job.tenant_id, field_name="tenant id"),
                    requested_by=job.requested_by,
                    status=job.status.value,
                    force=job.force,
                    batch_size=job.batch_size,
                    embedding_model=job.embedding_model,
                    embedding_dimensions=job.embedding_dimensions,
                    published_count=job.published_count,
                    current_count=job.current_count,
                    pending_count=job.pending_count,
                    embedded_count=job.embedded_count,
                    batch_count=job.batch_count,
                    error_code=job.error_code,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                )
            )
            try:
                await session.commit()
            except IntegrityError as error:
                if _sqlstate(error) == "23505":
                    raise ToolSearchReindexJobConflictError(
                        "an active reindex job already exists for tenant"
                    ) from error
                raise

    async def get(self, tenant_id: str, job_id: str) -> ToolSearchReindexJob | None:
        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session:
            model = await session.scalar(
                select(ToolSearchReindexJobModel).where(
                    ToolSearchReindexJobModel.tenant_id
                    == as_uuid(tenant_id, field_name="tenant id"),
                    ToolSearchReindexJobModel.id == as_uuid(job_id, field_name="reindex job id"),
                )
            )
            return _from_model(model) if model is not None else None

    async def list_recent(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[tuple[ToolSearchReindexJob, ...], int]:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session:
            total = int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(ToolSearchReindexJobModel)
                        .where(ToolSearchReindexJobModel.tenant_id == tenant_uuid)
                    )
                )
                or 0
            )
            models = (
                await session.scalars(
                    select(ToolSearchReindexJobModel)
                    .where(ToolSearchReindexJobModel.tenant_id == tenant_uuid)
                    .order_by(
                        ToolSearchReindexJobModel.created_at.desc(),
                        ToolSearchReindexJobModel.id.desc(),
                    )
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return tuple(_from_model(model) for model in models), total

    async def claim(
        self,
        tenant_id: str,
        job_id: str,
        *,
        started_at: datetime,
    ) -> ToolSearchReindexJob | None:
        async with _locked_model(self._database_runtime, tenant_id, job_id) as locked:
            model, session = locked
            if model is None or model.status != ToolSearchReindexJobStatus.PENDING.value:
                return None
            model.status = ToolSearchReindexJobStatus.RUNNING.value
            model.started_at = started_at
            await session.commit()
            return _from_model(model)

    async def succeed(
        self,
        tenant_id: str,
        job_id: str,
        *,
        result: ReindexToolsResult,
        finished_at: datetime,
    ) -> None:
        async with _locked_model(self._database_runtime, tenant_id, job_id) as locked:
            model, session = locked
            if model is None:
                return
            model.status = ToolSearchReindexJobStatus.SUCCEEDED.value
            model.published_count = result.published_count
            model.current_count = result.current_count
            model.pending_count = result.pending_count
            model.embedded_count = result.embedded_count
            model.batch_count = result.batch_count
            model.error_code = None
            model.finished_at = finished_at
            await session.commit()

    async def fail(
        self,
        tenant_id: str,
        job_id: str,
        *,
        error_code: str,
        finished_at: datetime,
    ) -> None:
        async with _locked_model(self._database_runtime, tenant_id, job_id) as locked:
            model, session = locked
            if model is None:
                return
            model.status = ToolSearchReindexJobStatus.FAILED.value
            model.error_code = error_code
            model.finished_at = finished_at
            await session.commit()

    async def recover_interrupted(
        self,
        tenant_id: str,
        *,
        finished_at: datetime,
    ) -> int:
        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session:
            active_filter = (
                ToolSearchReindexJobModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                ToolSearchReindexJobModel.status.in_(
                    (
                        ToolSearchReindexJobStatus.PENDING.value,
                        ToolSearchReindexJobStatus.RUNNING.value,
                    )
                ),
            )
            recovered_count = int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(ToolSearchReindexJobModel)
                        .where(*active_filter)
                    )
                )
                or 0
            )
            await session.execute(
                update(ToolSearchReindexJobModel)
                .where(*active_filter)
                .values(
                    status=ToolSearchReindexJobStatus.FAILED.value,
                    error_code="reindex_job_interrupted",
                    finished_at=finished_at,
                )
            )
            await session.commit()
            return recovered_count


@asynccontextmanager
async def _locked_model(
    database_runtime: DatabaseRuntimePort,
    tenant_id: str,
    job_id: str,
) -> AsyncGenerator[tuple[ToolSearchReindexJobModel | None, AsyncSession], None]:
    session = database_runtime.require_session_factory()()
    try:
        model = await session.scalar(
            select(ToolSearchReindexJobModel)
            .where(
                ToolSearchReindexJobModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                ToolSearchReindexJobModel.id == as_uuid(job_id, field_name="reindex job id"),
            )
            .with_for_update()
        )
        yield model, session
    finally:
        if session.in_transaction():
            await session.rollback()
        await session.close()


def _from_model(model: ToolSearchReindexJobModel) -> ToolSearchReindexJob:
    return ToolSearchReindexJob(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        requested_by=model.requested_by,
        status=ToolSearchReindexJobStatus(model.status),
        force=model.force,
        batch_size=model.batch_size,
        embedding_model=model.embedding_model,
        embedding_dimensions=model.embedding_dimensions,
        published_count=model.published_count,
        current_count=model.current_count,
        pending_count=model.pending_count,
        embedded_count=model.embedded_count,
        batch_count=model.batch_count,
        error_code=model.error_code,
        created_at=model.created_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
    )


def _sqlstate(error: IntegrityError) -> str | None:
    return getattr(error.orig, "sqlstate", None)
