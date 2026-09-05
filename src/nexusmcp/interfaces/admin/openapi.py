"""Admin OpenAPI Contract 的无网络构建与确定性导出。"""

import json
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI

_CONTRACT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
_PLACEHOLDER_DATABASE_URL = (
    "postgresql+asyncpg://contract:contract@127.0.0.1:1/nexusmcp_contract_test"
)


def build_admin_openapi_document() -> dict[str, Any]:
    """只组装 Route/Schema；DatabaseRuntime 不进入 Lifespan，因此不会建立连接。"""

    # 局部 Import 避免 Bootstrap → Admin Package 初始化时形成反向 Import Cycle。
    from nexusmcp.bootstrap.app import create_app
    from nexusmcp.bootstrap.config import Settings

    app = create_app(
        Settings.model_validate(
            {
                "environment": "test",
                "catalog_backend": "postgresql",
                "database_url": _PLACEHOLDER_DATABASE_URL,
                "local_tenant_id": _CONTRACT_TENANT_ID,
                "control_plane_enabled": True,
                "admin_identity_mode": "public_demo",
                "tool_execution_enabled": False,
                "embedding_api_key": None,
                "telemetry_enabled": False,
                "upstream_egress_policy_enabled": False,
            }
        )
    )
    admin_app = cast(FastAPI | None, app.state.admin_app)
    if admin_app is None:  # pragma: no cover - 上述 Contract Settings 已明确开启
        raise RuntimeError("Admin OpenAPI app was not composed")
    return cast(dict[str, Any], admin_app.openapi())


def serialize_admin_openapi() -> str:
    return (
        json.dumps(
            build_admin_openapi_document(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def export_admin_openapi(output_path: Path) -> Path:
    resolved = output_path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(serialize_admin_openapi(), encoding="utf-8", newline="\n")
    return resolved
