"""Tool Binding 执行语义的确定性 Canonical JSON Digest。"""

import hashlib
import json

from nexusmcp.modules.connectors.domain import ToolBinding


def calculate_binding_digest(binding: ToolBinding) -> str:
    payload = {
        "binding_type": binding.binding_type.value,
        "upstream_service_id": binding.upstream_service_id,
        "binding_config": dict(binding.binding_config),
    }
    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
