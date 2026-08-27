"""Protocol Compatibility Matrix 的版本与 Pytest Evidence 防腐测试。"""

import json
from pathlib import Path
from typing import Any

MATRIX_PATH = (
    Path(__file__).resolve().parents[3] / "evals" / "protocol" / "compatibility_matrix.json"
)
PROJECT_ROOT = MATRIX_PATH.parents[2]


def test_protocol_matrix_covers_both_eras_and_references_real_tests() -> None:
    payload: dict[str, Any] = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    assert payload["sdk"] == "mcp==2.0.0"
    assert payload["modern_version"] == "2026-07-28"
    assert payload["legacy_version"] == "2025-11-25"
    cases: list[dict[str, Any]] = payload["cases"]
    assert len(cases) >= 15
    assert len({str(case["id"]) for case in cases}) == len(cases)
    assert {str(case["era"]) for case in cases} == {"both", "legacy", "modern"}

    for case in cases:
        relative_path, separator, node_name = str(case["evidence"]).partition("::")
        assert separator and node_name.startswith("test_"), case["id"]
        path = PROJECT_ROOT / relative_path
        assert path.is_file(), case["id"]
        assert f"def {node_name}(" in path.read_text(encoding="utf-8"), case["id"]
