"""OpenAPI 3 Local Document 的校验、Local $ref 解析与标准化。"""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import replace
from typing import Any

from nexusmcp.modules.openapi_import.domain import (
    OperationConflictStatus,
    ParsedOpenApiDocument,
    ParsedOperation,
)
from nexusmcp.shared.errors import (
    OpenApiDocumentInvalidError,
    OpenApiFeatureUnsupportedError,
)

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")
_PARAMETER_LOCATIONS = {"path", "query", "header"}
_SIDE_EFFECTS = {
    "read_only",
    "idempotent_write",
    "non_idempotent_write",
    "unknown",
}
_NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_NON_IDENTIFIER = re.compile(r"[^a-zA-Z0-9]+")
_MAX_REF_DEPTH = 32


class OpenApiParser:
    def parse(
        self,
        document: Mapping[str, Any],
        *,
        namespace: str,
        operation_allowlist: Sequence[str] = (),
    ) -> ParsedOpenApiDocument:
        if not _NAMESPACE_PATTERN.fullmatch(namespace):
            raise OpenApiDocumentInvalidError("upstream namespace is not a valid tool namespace")
        openapi_version = document.get("openapi")
        if not isinstance(openapi_version, str) or not openapi_version.startswith(("3.0.", "3.1.")):
            raise OpenApiFeatureUnsupportedError("only OpenAPI 3.0 and 3.1 are supported")
        paths = _require_mapping(document.get("paths"), "OpenAPI paths")
        allowlist = set(operation_allowlist)
        operations: list[ParsedOperation] = []

        for path in sorted(paths):
            if not isinstance(path, str) or not path.startswith("/"):
                raise OpenApiDocumentInvalidError("OpenAPI path must start with slash")
            path_item = _require_mapping(paths[path], f"path item {path}")
            path_parameters = _require_sequence(path_item.get("parameters", ()), "path parameters")
            for method in _HTTP_METHODS:
                raw_operation = path_item.get(method)
                if raw_operation is None:
                    continue
                operation = _require_mapping(raw_operation, f"operation {method} {path}")
                operation_id_value = operation.get("operationId")
                operation_id = (
                    operation_id_value.strip()
                    if isinstance(operation_id_value, str) and operation_id_value.strip()
                    else None
                )
                operation_key = f"{method.upper()} {path}"
                if allowlist and operation_key not in allowlist and operation_id not in allowlist:
                    continue
                operations.append(
                    self._parse_operation(
                        document,
                        namespace=namespace,
                        method=method,
                        path=path,
                        operation_key=operation_key,
                        operation_id=operation_id,
                        operation=operation,
                        path_parameters=path_parameters,
                    )
                )

        if not operations:
            raise OpenApiDocumentInvalidError("OpenAPI document did not contain allowed operations")
        name_counts = Counter(
            operation.generated_tool_name
            for operation in operations
            if operation.generated_tool_name is not None
        )
        resolved_operations = tuple(
            replace(operation, conflict_status=OperationConflictStatus.NAME_COLLISION)
            if operation.generated_tool_name is not None
            and name_counts[operation.generated_tool_name] > 1
            and operation.conflict_status is OperationConflictStatus.NONE
            else operation
            for operation in operations
        )
        return ParsedOpenApiDocument(
            openapi_version=openapi_version,
            operations=resolved_operations,
        )

    def _parse_operation(
        self,
        document: Mapping[str, Any],
        *,
        namespace: str,
        method: str,
        path: str,
        operation_key: str,
        operation_id: str | None,
        operation: Mapping[str, Any],
        path_parameters: Sequence[Any],
    ) -> ParsedOperation:
        conflict = (
            OperationConflictStatus.MISSING_OPERATION_ID
            if operation_id is None
            else OperationConflictStatus.NONE
        )
        combined_parameters = _merge_parameters(
            path_parameters,
            _require_sequence(operation.get("parameters", ()), "operation parameters"),
            document,
        )
        normalized_parameters: list[dict[str, Any]] = []
        input_properties: dict[str, Any] = {}
        required_arguments: list[str] = []

        for parameter in combined_parameters:
            location = parameter.get("in")
            name = parameter.get("name")
            if location not in _PARAMETER_LOCATIONS or not isinstance(name, str) or not name:
                conflict = OperationConflictStatus.UNSUPPORTED
                continue
            argument_name = _argument_name(name)
            if argument_name in input_properties:
                argument_name = f"{location}_{argument_name}"
            schema = _require_mapping(parameter.get("schema", {}), "parameter schema")
            resolved_schema = _resolve_node(schema, document)
            required = location == "path" or parameter.get("required") is True
            normalized_parameters.append(
                {
                    "argument_name": argument_name,
                    "upstream_name": name,
                    "location": location,
                    "required": required,
                    "schema": resolved_schema,
                }
            )
            input_properties[argument_name] = resolved_schema
            if required:
                required_arguments.append(argument_name)

        request_body, body_unsupported = _normalize_request_body(
            operation.get("requestBody"),
            document,
        )
        if body_unsupported:
            conflict = OperationConflictStatus.UNSUPPORTED
        if request_body is not None:
            input_properties["body"] = request_body["schema"]
            if request_body["required"]:
                required_arguments.append("body")

        responses, output_schema, response_unsupported = _normalize_responses(
            operation.get("responses"),
            document,
        )
        if response_unsupported:
            conflict = OperationConflictStatus.UNSUPPORTED

        generated_tool_name = _generated_tool_name(namespace, operation_id, method, path)
        side_effect = _side_effect(operation, method)
        normalized_operation = {
            "operation_id": operation_id,
            "summary": _optional_text(operation.get("summary")),
            "description": _optional_text(operation.get("description")),
            "method": method.upper(),
            "path": path,
            "tags": _string_list(operation.get("tags", ())),
            "parameters": normalized_parameters,
            "request_body": request_body,
            "responses": responses,
            "security": _normalize_security(operation.get("security", ())),
            "side_effect": side_effect,
            "tool_input_schema": {
                "type": "object",
                "properties": input_properties,
                "required": required_arguments,
                "additionalProperties": False,
            },
            "tool_output_schema": output_schema,
        }
        return ParsedOperation(
            operation_key=operation_key,
            operation_id=operation_id,
            method=method.upper(),
            path=path,
            normalized_operation=normalized_operation,
            generated_tool_name=generated_tool_name,
            conflict_status=conflict,
        )


def _merge_parameters(
    path_parameters: Sequence[Any],
    operation_parameters: Sequence[Any],
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    merged: dict[tuple[object, object], dict[str, Any]] = {}
    for raw_parameter in (*path_parameters, *operation_parameters):
        parameter = _require_mapping(
            _resolve_node(raw_parameter, document),
            "OpenAPI parameter",
        )
        merged[(parameter.get("name"), parameter.get("in"))] = dict(parameter)
    return tuple(merged.values())


def _normalize_request_body(
    raw_request_body: object,
    document: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, bool]:
    if raw_request_body is None:
        return None, False
    request_body = _require_mapping(
        _resolve_node(raw_request_body, document),
        "request body",
    )
    content = _require_mapping(request_body.get("content"), "request body content")
    media_type = content.get("application/json")
    if media_type is None:
        return None, True
    media = _require_mapping(media_type, "application/json request body")
    schema = _require_mapping(media.get("schema", {}), "request body schema")
    return (
        {
            "argument_name": "body",
            "required": request_body.get("required") is True,
            "content_type": "application/json",
            "schema": _resolve_node(schema, document),
        },
        False,
    )


def _normalize_responses(
    raw_responses: object,
    document: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, bool]:
    responses = _require_mapping(raw_responses, "operation responses")
    normalized: list[dict[str, Any]] = []
    output_schema: dict[str, Any] | None = None
    unsupported = False
    for status_code in sorted(responses):
        response = _require_mapping(
            _resolve_node(responses[status_code], document),
            f"response {status_code}",
        )
        raw_content = response.get("content", {})
        content = _require_mapping(raw_content, f"response {status_code} content")
        content_types = sorted(str(content_type) for content_type in content)
        schema: dict[str, Any] | None = None
        json_media = content.get("application/json")
        if json_media is not None:
            media = _require_mapping(json_media, "response application/json")
            raw_schema = _require_mapping(media.get("schema", {}), "response schema")
            schema = _resolve_node(raw_schema, document)
            if str(status_code).startswith("2") and output_schema is None:
                output_schema = schema
        elif content:
            unsupported = True
        normalized.append(
            {
                "status_code": str(status_code),
                "description": _optional_text(response.get("description")),
                "content_types": content_types,
                "schema": schema,
            }
        )
    return normalized, output_schema, unsupported


def _resolve_node(
    value: object,
    document: Mapping[str, Any],
    *,
    stack: tuple[str, ...] = (),
    depth: int = 0,
) -> Any:
    if depth > _MAX_REF_DEPTH:
        raise OpenApiFeatureUnsupportedError("OpenAPI reference depth exceeded")
    if isinstance(value, list):
        return [_resolve_node(item, document, stack=stack, depth=depth + 1) for item in value]
    if not isinstance(value, Mapping):
        return deepcopy(value)
    reference = value.get("$ref")
    if reference is not None:
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise OpenApiFeatureUnsupportedError("only local OpenAPI references are supported")
        if reference in stack:
            raise OpenApiFeatureUnsupportedError("cyclic OpenAPI references are not supported")
        target = _resolve_pointer(document, reference)
        resolved = _require_mapping(
            _resolve_node(target, document, stack=(*stack, reference), depth=depth + 1),
            f"reference {reference}",
        )
        siblings = {key: item for key, item in value.items() if key != "$ref"}
        return {
            **resolved,
            **_resolve_node(siblings, document, stack=stack, depth=depth + 1),
        }
    return {
        str(key): _resolve_node(item, document, stack=stack, depth=depth + 1)
        for key, item in value.items()
        if key not in {"example", "examples"}
    }


def _resolve_pointer(document: Mapping[str, Any], reference: str) -> object:
    current: object = document
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            raise OpenApiDocumentInvalidError(f"OpenAPI reference {reference} was not found")
        current = current[part]
    return current


def _generated_tool_name(
    namespace: str,
    operation_id: str | None,
    method: str,
    path: str,
) -> str:
    candidate = operation_id or f"{method}_{path}"
    snake = _CAMEL_BOUNDARY.sub(r"\1_\2", candidate)
    snake = _NON_IDENTIFIER.sub("_", snake).strip("_").lower()
    return f"{namespace}.{snake}"


def _argument_name(name: str) -> str:
    return _NON_IDENTIFIER.sub("_", name).strip("_").lower()


def _side_effect(operation: Mapping[str, Any], method: str) -> str:
    declared = operation.get("x-nexusmcp-side-effect")
    if isinstance(declared, str) and declared in _SIDE_EFFECTS:
        return declared
    if method == "get":
        return "read_only"
    if method in {"put", "delete"}:
        return "idempotent_write"
    if method == "post":
        return "non_idempotent_write"
    return "unknown"


def _normalize_security(value: object) -> list[dict[str, list[str]]]:
    if value is None:
        return []
    requirements = _require_sequence(value, "security requirements")
    normalized: list[dict[str, list[str]]] = []
    for requirement in requirements:
        mapping = _require_mapping(requirement, "security requirement")
        normalized.append({str(name): _string_list(scopes) for name, scopes in mapping.items()})
    return normalized


def _string_list(value: object) -> list[str]:
    sequence = _require_sequence(value, "string list")
    if not all(isinstance(item, str) for item in sequence):
        raise OpenApiDocumentInvalidError("OpenAPI string list contained non-string value")
    return [str(item) for item in sequence]


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _require_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OpenApiDocumentInvalidError(f"{field_name} must be an object")
    return value


def _require_sequence(value: object, field_name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise OpenApiDocumentInvalidError(f"{field_name} must be an array")
    return value
