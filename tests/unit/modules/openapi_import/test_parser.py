"""OpenAPI Parser 的冲突、Allowlist 与不支持特性测试。"""

import pytest

from nexusmcp.modules.openapi_import.domain import OperationConflictStatus
from nexusmcp.modules.openapi_import.parser import OpenApiParser
from nexusmcp.shared.errors import OpenApiFeatureUnsupportedError


def _document(paths: dict[str, object]) -> dict[str, object]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "1"},
        "paths": paths,
    }


def _operation(
    operation_id: str | None, *, content_type: str = "application/json"
) -> dict[str, object]:
    operation: dict[str, object] = {
        "responses": {
            "200": {
                "description": "ok",
                "content": {content_type: {"schema": {"type": "object"}}},
            }
        }
    }
    if operation_id is not None:
        operation["operationId"] = operation_id
    return operation


def test_parser_marks_missing_operation_id_and_generated_name_collision() -> None:
    missing = OpenApiParser().parse(
        _document({"/items": {"get": _operation(None)}}),
        namespace="inventory",
    )
    collision = OpenApiParser().parse(
        _document(
            {
                "/items": {"get": _operation("listItems")},
                "/products": {"get": _operation("listItems")},
            }
        ),
        namespace="inventory",
    )

    assert missing.operations[0].conflict_status is OperationConflictStatus.MISSING_OPERATION_ID
    assert all(
        operation.conflict_status is OperationConflictStatus.NAME_COLLISION
        for operation in collision.operations
    )


def test_parser_applies_operation_allowlist_and_marks_binary_response() -> None:
    parsed = OpenApiParser().parse(
        _document(
            {
                "/items": {"get": _operation("listItems")},
                "/export": {
                    "get": _operation("exportItems", content_type="application/octet-stream")
                },
            }
        ),
        namespace="inventory",
        operation_allowlist=["exportItems"],
    )

    assert len(parsed.operations) == 1
    assert parsed.operations[0].conflict_status is OperationConflictStatus.UNSUPPORTED


def test_parser_rejects_remote_and_cyclic_refs() -> None:
    remote = _document(
        {
            "/items": {
                "get": {
                    "parameters": [{"$ref": "https://example.test/parameters.json"}],
                    **_operation("listItems"),
                }
            }
        }
    )
    cyclic = _document(
        {
            "/items": {
                "get": {
                    **_operation("listItems"),
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Node"}
                                }
                            },
                        }
                    },
                }
            }
        }
    )
    cyclic["components"] = {
        "schemas": {
            "Node": {
                "type": "object",
                "properties": {"next": {"$ref": "#/components/schemas/Node"}},
            }
        }
    }

    with pytest.raises(OpenApiFeatureUnsupportedError, match="local"):
        OpenApiParser().parse(remote, namespace="inventory")
    with pytest.raises(OpenApiFeatureUnsupportedError, match="cyclic"):
        OpenApiParser().parse(cyclic, namespace="inventory")
