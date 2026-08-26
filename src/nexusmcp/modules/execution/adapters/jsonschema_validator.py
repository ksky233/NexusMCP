"""动态 Tool Input Schema 的 JSON Schema Validator Adapter。"""

from collections.abc import Mapping
from typing import Any

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

from nexusmcp.shared.errors import InvalidArgumentsError


class JsonSchemaArgumentsValidator:
    def validate(
        self,
        schema: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> None:
        schema_dict = dict(schema)
        validator_class = validator_for(schema_dict)
        try:
            validator_class.check_schema(schema_dict)
        except SchemaError:
            raise InvalidArgumentsError("published tool input schema is invalid") from None
        errors = sorted(
            validator_class(schema_dict).iter_errors(dict(arguments)),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if not errors:
            return
        first = errors[0]
        path = ".".join(str(part) for part in first.absolute_path) or "$"
        # 不把失败值写入 Exception，避免 Arguments 经日志或错误响应泄漏。
        raise InvalidArgumentsError(f"tool arguments failed {first.validator} validation at {path}")
