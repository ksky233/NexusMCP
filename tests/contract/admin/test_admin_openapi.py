"""Admin OpenAPI Operation、Problem Details 与 Snapshot Drift Contract。"""

import json
from pathlib import Path
from typing import Any

from nexusmcp.interfaces.admin.openapi import (
    build_admin_openapi_document,
    export_admin_openapi,
    serialize_admin_openapi,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = PROJECT_ROOT / "contracts" / "admin.openapi.json"
EXPECTED_OPERATION_IDS = {
    "activateToolset",
    "approveApproval",
    "disableUpstream",
    "getApproval",
    "getDashboard",
    "getExecution",
    "getOpenApiImport",
    "getSearchProjectionStatus",
    "getTool",
    "getToolBinding",
    "getToolVersion",
    "getToolVersionBinding",
    "getToolSearchIndexStatus",
    "getToolSearchReindexJob",
    "getUpstream",
    "listUpstreams",
    "listApprovals",
    "listAuditEvents",
    "listExecutionAttempts",
    "listExecutions",
    "listOpenApiImports",
    "listReviewOperations",
    "listTools",
    "listToolVersions",
    "listToolSearchReindexJobs",
    "publishToolVersion",
    "registerUpstream",
    "createToolSearchReindexJob",
    "createToolset",
    "disableToolset",
    "getToolset",
    "listToolsets",
    "replaceToolsetAccessGrants",
    "replaceToolsetMembers",
    "rejectApproval",
    "resetDemoWorkspace",
    "reviewImportedOperation",
    "searchCatalog",
    "searchTools",
    "submitOpenApiImport",
    "submitToolVersionReview",
    "updateUpstream",
    "updateToolset",
}


def test_admin_openapi_has_stable_operations_and_http_only_upstream_input() -> None:
    document = build_admin_openapi_document()

    assert document["openapi"] == "3.1.0"
    operation_ids = _operation_ids(document)
    assert operation_ids == EXPECTED_OPERATION_IDS
    register_schema = document["components"]["schemas"]["RegisterUpstreamRequest"]
    assert register_schema["properties"]["service_type"]["enum"] == ["http"]
    assert register_schema["properties"]["transport_type"]["enum"] == ["http"]
    upstream_page = document["components"]["schemas"]["UpstreamPageResponse"]
    assert upstream_page["required"] == ["items", "page"]
    page_metadata = document["components"]["schemas"]["PageMetadata"]
    assert page_metadata["required"] == ["offset", "limit", "total"]


def test_admin_openapi_declares_problem_json_for_expected_and_validation_errors() -> None:
    document = build_admin_openapi_document()
    problem_schema = document["components"]["schemas"]["ProblemDetails"]

    assert {
        "type",
        "title",
        "status",
        "detail",
        "code",
    } <= set(problem_schema["required"])
    for path_item in document["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            validation_response = operation["responses"]["422"]
            assert set(validation_response["content"]) == {"application/problem+json"}
            assert validation_response["content"]["application/problem+json"]["schema"] == {
                "$ref": "#/components/schemas/ProblemDetails"
            }


def test_admin_query_contract_uses_page_envelopes_and_redacted_operational_fields() -> None:
    document = build_admin_openapi_document()
    schemas = document["components"]["schemas"]

    for schema_name in (
        "UpstreamPageResponse",
        "ImportJobPageResponse",
        "ReviewOperationPageResponse",
        "ToolPageResponse",
        "ToolVersionPageResponse",
        "ApprovalPageResponse",
        "ExecutionPageResponse",
        "ExecutionAttemptPageResponse",
        "AuditEventPageResponse",
        "ToolSearchReindexJobPageResponse",
        "ToolsetPageResponse",
    ):
        assert schemas[schema_name]["required"] == ["items", "page"]

    assert schemas["UpstreamDetailResponse"]["properties"]["service_type"]["const"] == "http"
    assert schemas["ToolBindingDetailResponse"]["properties"]["binding_type"]["const"] == ("http")
    approval_fields = set(schemas["ApprovalSummaryResponse"]["properties"])
    execution_fields = set(schemas["ExecutionSummaryResponse"]["properties"])
    audit_fields = set(schemas["AuditEventResponse"]["properties"])
    assert "idempotency_key" not in approval_fields | execution_fields
    assert "has_idempotency_key" in approval_fields & execution_fields
    assert {"arguments", "result", "credential", "token"}.isdisjoint(audit_fields)


def test_admin_openapi_export_is_deterministic_and_matches_committed_snapshot(
    tmp_path: Path,
) -> None:
    first = export_admin_openapi(tmp_path / "first.json")
    second = export_admin_openapi(tmp_path / "second.json")

    assert first.read_bytes() == second.read_bytes()
    assert first.read_text(encoding="utf-8") == serialize_admin_openapi()
    assert json.loads(CONTRACT_PATH.read_text(encoding="utf-8")) == (build_admin_openapi_document())


def _operation_ids(document: dict[str, Any]) -> set[str]:
    return {
        str(operation["operationId"])
        for path_item in document["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
