"""显式启用的 SiliconFlow Embedding 付费网络 Smoke Test。"""

import math
import os
from collections.abc import Mapping
from time import perf_counter

import httpx
import pytest

from nexusmcp.bootstrap.config import Settings

pytestmark = [
    pytest.mark.external,
    pytest.mark.skipif(
        os.getenv("NEXUSMCP_RUN_EXTERNAL_TESTS") != "1",
        reason="set NEXUSMCP_RUN_EXTERNAL_TESTS=1 to call the paid embedding API",
    ),
]


@pytest.mark.asyncio
async def test_siliconflow_qwen3_embedding_returns_configured_dimensions() -> None:
    settings = Settings()
    api_key = settings.embedding_api_key
    if api_key is None:
        pytest.skip("NEXUSMCP_EMBEDDING_API_KEY is not configured")
    inputs = [
        (
            "Canonical Name: inventory.set_reorder_level\n"
            "Description: Set the desired reorder level for one SKU and warehouse.\n"
            "Inputs: sku, warehouse_id, reorder_level"
        ),
        "设置库存补货阈值",
    ]
    started_at = perf_counter()
    async with httpx.AsyncClient(trust_env=False, timeout=60.0) as client:
        response = await client.post(
            settings.embedding_api_url,
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            json={
                "model": settings.embedding_model,
                "input": inputs,
                "encoding_format": "float",
                "dimensions": settings.embedding_dimensions,
            },
        )
    if response.status_code != 200:
        pytest.fail(f"embedding API returned HTTP {response.status_code}")
    payload = response.json()
    assert isinstance(payload, Mapping)
    data = payload.get("data")
    assert isinstance(data, list) and len(data) == len(inputs)
    for item in data:
        assert isinstance(item, Mapping)
        embedding = item.get("embedding")
        assert isinstance(embedding, list)
        assert len(embedding) == settings.embedding_dimensions
        assert all(isinstance(value, int | float) and math.isfinite(value) for value in embedding)
        assert any(value != 0 for value in embedding)
    usage = payload.get("usage")
    total_tokens = usage.get("total_tokens") if isinstance(usage, Mapping) else None
    elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
    print(
        "SiliconFlow embedding smoke succeeded: "
        f"model={settings.embedding_model}, batch={len(data)}, "
        f"dimensions={settings.embedding_dimensions}, total_tokens={total_tokens}, "
        f"elapsed_ms={elapsed_ms}"
    )
