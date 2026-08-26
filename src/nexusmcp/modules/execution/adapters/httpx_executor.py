"""HTTP ToolBinding 的 httpx Async Executor。"""

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.connectors.domain import ToolBindingType
from nexusmcp.modules.credentials.domain import (
    CredentialInjectionLocation,
    CredentialValueFormat,
    ResolvedCredential,
)
from nexusmcp.modules.execution.domain import (
    ExecutionErrorCategory,
    ExecutorFailure,
    ExecutorRequest,
    ExecutorResult,
)


class HttpxToolExecutor:
    def __init__(self, client: httpx.AsyncClient, *, max_response_bytes: int = 1_048_576) -> None:
        if max_response_bytes <= 0:
            raise ValueError("max response bytes must be positive")
        self._client = client
        self._max_response_bytes = max_response_bytes

    async def execute(
        self,
        request: ExecutorRequest,
        credential: ResolvedCredential | None,
    ) -> ExecutorResult:
        tool = request.tool
        if tool.binding_type is not ToolBindingType.HTTP:
            raise ExecutorFailure(
                code="unsupported_binding_type",
                category=ExecutionErrorCategory.VALIDATION,
            )
        config = tool.binding_config
        method = str(config.get("method", "")).upper()
        if method not in {"GET", "PUT"}:
            raise ExecutorFailure(
                code="write_execution_not_enabled",
                category=ExecutionErrorCategory.AUTHORIZATION,
            )
        if method == "PUT" and tool.side_effect is not ToolSideEffect.IDEMPOTENT_WRITE:
            raise ExecutorFailure(
                code="put_tool_must_be_idempotent_write",
                category=ExecutionErrorCategory.AUTHORIZATION,
            )
        if method == "PUT" and request.idempotency_key is None:
            raise ExecutorFailure(
                code="idempotency_key_required",
                category=ExecutionErrorCategory.VALIDATION,
            )
        if method == "GET" and config.get("request_body") is not None:
            raise ExecutorFailure(
                code="get_binding_must_not_have_request_body",
                category=ExecutionErrorCategory.VALIDATION,
            )

        path_template = str(config.get("path_template", ""))
        if not path_template.startswith("/"):
            raise ExecutorFailure(
                code="invalid_path_template",
                category=ExecutionErrorCategory.VALIDATION,
            )
        path, query, headers = _map_arguments(
            path_template,
            config.get("parameters", ()),
            request.arguments,
        )
        body = _map_request_body(method, config.get("request_body"), request.arguments)
        if request.idempotency_key is not None:
            _set_trusted_header(headers, "Idempotency-Key", request.idempotency_key)
        _inject_credential(query, headers, credential)
        url = f"{tool.upstream_endpoint.rstrip('/')}{path}"
        try:
            response = await self._client.request(
                method,
                url,
                params=query,
                headers=headers,
                json=body,
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException:
            raise ExecutorFailure(
                code="upstream_timeout",
                category=ExecutionErrorCategory.TIMEOUT_AFTER_SEND,
                outcome_unknown=True,
            ) from None
        except httpx.NetworkError:
            raise ExecutorFailure(
                code="upstream_network_error",
                category=ExecutionErrorCategory.NETWORK,
            ) from None

        if 400 <= response.status_code < 500:
            raise ExecutorFailure(
                code=f"upstream_{response.status_code}",
                category=ExecutionErrorCategory.UPSTREAM_4XX,
                upstream_status=response.status_code,
            )
        if response.status_code >= 500:
            raise ExecutorFailure(
                code=f"upstream_{response.status_code}",
                category=ExecutionErrorCategory.UPSTREAM_5XX,
                upstream_status=response.status_code,
            )
        if not 200 <= response.status_code < 300:
            raise ExecutorFailure(
                code=f"upstream_{response.status_code}",
                category=ExecutionErrorCategory.UNKNOWN,
                upstream_status=response.status_code,
            )
        if len(response.content) > self._max_response_bytes:
            raise ExecutorFailure(
                code="upstream_response_too_large",
                category=ExecutionErrorCategory.UNKNOWN,
            )

        content_type = response.headers.get("content-type", "").split(";", 1)[0] or None
        try:
            data: Any = response.json() if content_type == "application/json" else response.text
        except ValueError:
            raise ExecutorFailure(
                code="upstream_invalid_json",
                category=ExecutionErrorCategory.UNKNOWN,
            ) from None
        return ExecutorResult(
            data=data,
            content_type=content_type,
            upstream_status=response.status_code,
        )


def _map_arguments(
    path_template: str,
    raw_parameters: object,
    arguments: Mapping[str, Any],
) -> tuple[str, dict[str, str], dict[str, str]]:
    if not isinstance(raw_parameters, list):
        raise ExecutorFailure(
            code="invalid_parameter_mapping",
            category=ExecutionErrorCategory.VALIDATION,
        )
    path = path_template
    query: dict[str, str] = {}
    headers: dict[str, str] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, Mapping):
            raise ExecutorFailure(
                code="invalid_parameter_mapping",
                category=ExecutionErrorCategory.VALIDATION,
            )
        argument_name = str(raw_parameter.get("argument_name", ""))
        upstream_name = str(raw_parameter.get("upstream_name", ""))
        location = str(raw_parameter.get("location", ""))
        if argument_name not in arguments:
            if raw_parameter.get("required") is True:
                raise ExecutorFailure(
                    code="required_argument_missing_after_validation",
                    category=ExecutionErrorCategory.VALIDATION,
                )
            continue
        value = str(arguments[argument_name])
        if location == "path":
            placeholder = "{" + upstream_name + "}"
            if placeholder not in path:
                raise ExecutorFailure(
                    code="path_parameter_placeholder_missing",
                    category=ExecutionErrorCategory.VALIDATION,
                )
            path = path.replace(placeholder, quote(value, safe=""))
        elif location == "query":
            query[upstream_name] = value
        elif location == "header":
            headers[upstream_name] = value
        else:
            raise ExecutorFailure(
                code="unsupported_parameter_location",
                category=ExecutionErrorCategory.VALIDATION,
            )
    return path, query, headers


def _inject_credential(
    query: dict[str, str],
    headers: dict[str, str],
    credential: ResolvedCredential | None,
) -> None:
    if credential is None:
        return
    value = credential.value.reveal()
    if credential.value_format is CredentialValueFormat.BEARER:
        value = f"Bearer {value}"
    if credential.injection_location is CredentialInjectionLocation.HEADER:
        _set_trusted_header(headers, credential.injection_name, value)
    elif credential.injection_location is CredentialInjectionLocation.QUERY:
        query[credential.injection_name] = value


def _map_request_body(
    method: str,
    raw_request_body: object,
    arguments: Mapping[str, Any],
) -> Any:
    if method == "GET":
        return None
    if not isinstance(raw_request_body, Mapping):
        raise ExecutorFailure(
            code="put_binding_requires_json_body",
            category=ExecutionErrorCategory.VALIDATION,
        )
    if raw_request_body.get("content_type") != "application/json":
        raise ExecutorFailure(
            code="unsupported_request_body_content_type",
            category=ExecutionErrorCategory.VALIDATION,
        )
    argument_name = str(raw_request_body.get("argument_name", ""))
    if argument_name not in arguments:
        if raw_request_body.get("required") is True:
            raise ExecutorFailure(
                code="required_request_body_missing_after_validation",
                category=ExecutionErrorCategory.VALIDATION,
            )
        return None
    return arguments[argument_name]


def _set_trusted_header(headers: dict[str, str], name: str, value: str) -> None:
    # HTTP Header 名称大小写不敏感，先删除客户端同名输入，避免形成双 Header。
    for header_name in tuple(headers):
        if header_name.lower() == name.lower():
            del headers[header_name]
    headers[name] = value
