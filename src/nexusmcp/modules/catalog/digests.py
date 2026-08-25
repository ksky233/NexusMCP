"""Tool Schema 的确定性 Canonical JSON Digest。"""

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def calculate_schema_digest(
    input_schema: Mapping[str, Any],
    output_schema: Mapping[str, Any] | None,
) -> str:
    payload = {
        "input_schema": dict(input_schema),
        "output_schema": dict(output_schema) if output_schema is not None else None,
    }
    return _sha256_json(payload)


def _sha256_json(value: object) -> str:
    canonical_json = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
