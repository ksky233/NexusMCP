"""Reindex CLI 参数到安全统计输出的 Adapter 测试。"""

import sys
from pathlib import Path

import pytest

from nexusmcp.interfaces.cli import app as cli_app
from nexusmcp.modules.tool_search.reindex_tools import ReindexToolsResult


def test_reindex_cli_prints_projection_statistics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_run(_arguments):
        return ReindexToolsResult(
            published_count=8,
            current_count=5,
            pending_count=3,
            embedded_count=3,
            batch_count=1,
            model="Qwen/Qwen3-Embedding-8B",
            dimensions=2048,
            dry_run=False,
        )

    monkeypatch.setattr(cli_app, "_run_reindex", fake_run)
    monkeypatch.setattr(sys, "argv", ["nexusmcp", "reindex-tools", "--batch-size", "8"])

    cli_app.main()

    output = capsys.readouterr().out
    assert "Published Tools: 8" in output
    assert "Embedded: 3" in output
    assert "Dimensions: 2048" in output


def test_export_admin_openapi_cli_reports_resolved_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "admin.openapi.json"

    def fake_export(path: Path) -> Path:
        assert path == output_path
        return output_path.resolve()

    monkeypatch.setattr(cli_app, "export_admin_openapi", fake_export)
    monkeypatch.setattr(
        sys,
        "argv",
        ["nexusmcp", "export-admin-openapi", "--output", str(output_path)],
    )

    cli_app.main()

    assert f"Admin OpenAPI: {output_path.resolve()}" in capsys.readouterr().out
