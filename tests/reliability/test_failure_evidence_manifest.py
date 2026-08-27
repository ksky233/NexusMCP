"""Failure Injection Matrix 的组件覆盖与 Pytest Evidence 防腐测试。"""

import json
from pathlib import Path
from typing import Any

MATRIX_PATH = (
    Path(__file__).resolve().parents[2] / "evals" / "reliability" / "failure_injection_cases.json"
)
PROJECT_ROOT = MATRIX_PATH.parents[2]


def test_failure_matrix_covers_critical_components_and_real_tests() -> None:
    payload: dict[str, Any] = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    cases: list[dict[str, Any]] = payload["cases"]
    assert len(cases) >= 14
    assert len({str(case["id"]) for case in cases}) == len(cases)
    assert {str(case["component"]) for case in cases} == {
        "approval",
        "catalog_transaction",
        "database",
        "egress",
        "embedding",
        "execution",
        "execution_transaction",
        "idempotency",
        "tool_search",
        "upstream",
    }

    for case in cases:
        relative_path, separator, node_name = str(case["evidence"]).partition("::")
        assert separator and node_name.startswith("test_"), case["id"]
        path = PROJECT_ROOT / relative_path
        assert path.is_file(), case["id"]
        assert f"def {node_name}(" in path.read_text(encoding="utf-8"), case["id"]
