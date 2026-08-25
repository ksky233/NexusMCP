"""OpenAPI Import Job、Operation 与 Parser 输出领域模型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any


class OpenApiSourceType(StrEnum):
    UPLOAD = "upload"
    LOCAL_FIXTURE = "local_fixture"
    URL = "url"


class ImportJobStatus(StrEnum):
    PENDING = "pending"
    VALIDATING = "validating"
    PARSING = "parsing"
    COMPLETED = "completed"
    FAILED = "failed"


class OperationReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_CHANGE = "needs_change"


class OperationConflictStatus(StrEnum):
    NONE = "none"
    NAME_COLLISION = "name_collision"
    MISSING_OPERATION_ID = "missing_operation_id"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class OpenApiImportJob:
    id: str
    tenant_id: str
    upstream_service_id: str
    source_type: OpenApiSourceType
    source_ref: str
    source_digest: str
    openapi_version: str | None
    operation_allowlist: tuple[str, ...]
    allowlist_snapshot: Mapping[str, Any]
    status: ImportJobStatus
    error_summary: str | None
    created_by: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def start_validation(self, started_at: datetime) -> OpenApiImportJob:
        if self.status is not ImportJobStatus.PENDING:
            raise ValueError("only pending import job can start validation")
        return replace(
            self,
            status=ImportJobStatus.VALIDATING,
            started_at=started_at,
        )

    def start_parsing(self) -> OpenApiImportJob:
        if self.status is not ImportJobStatus.VALIDATING:
            raise ValueError("only validating import job can start parsing")
        return replace(self, status=ImportJobStatus.PARSING)

    def complete(self, openapi_version: str, completed_at: datetime) -> OpenApiImportJob:
        if self.status is not ImportJobStatus.PARSING:
            raise ValueError("only parsing import job can complete")
        return replace(
            self,
            status=ImportJobStatus.COMPLETED,
            openapi_version=openapi_version,
            completed_at=completed_at,
            error_summary=None,
        )

    def fail(self, error_summary: str, completed_at: datetime) -> OpenApiImportJob:
        if self.status in (ImportJobStatus.COMPLETED, ImportJobStatus.FAILED):
            raise ValueError("terminal import job cannot fail again")
        return replace(
            self,
            status=ImportJobStatus.FAILED,
            error_summary=error_summary,
            completed_at=completed_at,
        )


@dataclass(frozen=True, slots=True)
class ImportedOperation:
    id: str
    tenant_id: str
    import_job_id: str
    upstream_service_id: str
    operation_key: str
    operation_id: str | None
    method: str
    path: str
    normalized_operation: Mapping[str, Any]
    generated_tool_name: str | None
    conflict_status: OperationConflictStatus
    review_status: OperationReviewStatus
    review_notes: str | None = None
    draft_tool_version_id: str | None = None
    draft_tool_binding_id: str | None = None

    def accept(
        self,
        *,
        draft_tool_version_id: str,
        draft_tool_binding_id: str,
        review_notes: str | None,
    ) -> ImportedOperation:
        if self.conflict_status is not OperationConflictStatus.NONE:
            raise ValueError("operation with conflict cannot be accepted")
        if self.review_status not in (
            OperationReviewStatus.PENDING,
            OperationReviewStatus.NEEDS_CHANGE,
        ):
            raise ValueError("operation cannot be accepted from current review state")
        return replace(
            self,
            review_status=OperationReviewStatus.ACCEPTED,
            review_notes=review_notes,
            draft_tool_version_id=draft_tool_version_id,
            draft_tool_binding_id=draft_tool_binding_id,
        )


@dataclass(frozen=True, slots=True)
class ParsedOperation:
    operation_key: str
    operation_id: str | None
    method: str
    path: str
    normalized_operation: Mapping[str, Any]
    generated_tool_name: str | None
    conflict_status: OperationConflictStatus


@dataclass(frozen=True, slots=True)
class ParsedOpenApiDocument:
    openapi_version: str
    operations: tuple[ParsedOperation, ...]


@dataclass(frozen=True, slots=True)
class OpenApiDocument:
    source_ref: str
    source_digest: str
    content: Mapping[str, Any]
