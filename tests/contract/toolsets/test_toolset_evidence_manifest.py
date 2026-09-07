"""Toolset Evidence Manifest 的覆盖面与 Pytest Node 防腐测试。"""

import json
from pathlib import Path
from typing import Any

MATRIX_PATH = Path(__file__).resolve().parents[3] / "evals" / "toolsets" / "toolset_cases.json"
PROJECT_ROOT = MATRIX_PATH.parents[2]


def test_toolset_evidence_matrix_covers_boundaries_and_real_tests() -> None:
    payload: dict[str, Any] = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["modern_version"] == "2026-07-28"
    cases: list[dict[str, Any]] = payload["cases"]
    assert len(cases) >= 12
    assert len({str(case["id"]) for case in cases}) == len(cases)
    assert {str(case["category"]) for case in cases} == {
        "access",
        "audit",
        "bootstrap",
        "protocol",
        "search",
    }

    for case in cases:
        relative_path, separator, node_name = str(case["evidence"]).partition("::")
        assert separator and node_name.startswith("test_"), case["id"]
        path = PROJECT_ROOT / relative_path
        assert path.is_file(), case["id"]
        assert f"def {node_name}(" in path.read_text(encoding="utf-8"), case["id"]
