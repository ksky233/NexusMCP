"""Security Evidence Manifest 的覆盖面与 Pytest Node 引用防腐测试。"""

import json
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "evals" / "security" / "security_cases.json"
PROJECT_ROOT = MANIFEST_PATH.parents[2]


def test_security_manifest_references_existing_automated_evidence() -> None:
    payload: dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert payload["version"] == 2
    cases: list[dict[str, Any]] = payload["cases"]
    assert len(cases) >= 15
    assert len({str(case["id"]) for case in cases}) == len(cases)
    assert {str(case["category"]) for case in cases} == {
        "approval",
        "idempotency",
        "identity_policy",
        "secret",
        "ssrf",
        "tenant",
    }

    for case in cases:
        evidence = str(case["evidence"])
        relative_path, separator, node_name = evidence.partition("::")
        assert separator and node_name.startswith("test_"), case["id"]
        evidence_path = PROJECT_ROOT / relative_path
        assert evidence_path.is_file(), case["id"]
        source = evidence_path.read_text(encoding="utf-8")
        assert f"def {node_name}(" in source, case["id"]
