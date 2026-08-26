"""Demo 场景不能反向渗透 NexusMCP Core。"""

import ast
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[3] / "src" / "nexusmcp"
DEMO_NAMES = {"employee_directory", "operations", "inventory"}


def test_core_does_not_import_or_branch_on_demo_scenarios() -> None:
    violations: list[str] = []
    for source_path in CORE_ROOT.rglob("*.py"):
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
        if "examples.upstream_apis" in source:
            violations.append(f"{source_path}: imports Demo package")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.strip().lower() in DEMO_NAMES:
                    violations.append(
                        f"{source_path}:{node.lineno}: hard-codes Demo name {node.value!r}"
                    )

    assert violations == []
