"""敏感 Payload 只保留确定性摘要时使用的 Canonical JSON Digest。"""

import hashlib
import json


def canonical_json_digest(value: object) -> str:
    canonical_json = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
