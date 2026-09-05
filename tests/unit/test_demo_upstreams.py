"""单进程 Demo Upstreams 的路由冒烟测试。"""

import importlib
import sys
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
app = cast(FastAPI, importlib.import_module("examples.upstream_apis.app").app)


@pytest.mark.asyncio
async def test_combined_demo_upstreams_expose_three_scenarios_and_health() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        health = await client.get("/health/ready")
        employee = await client.get("/employee-directory/employees/emp-001")
        incident = await client.get("/operations/incidents/inc-001")
        inventory = await client.get(
            "/inventory/inventory/laptop-pro-14",
            params={"warehouse_id": "shanghai-01"},
        )

    assert health.json() == {"status": "ok"}
    assert employee.json()["name"] == "Ada Chen"
    assert incident.json()["service"] == "checkout-api"
    assert inventory.json()["available"] == 80
