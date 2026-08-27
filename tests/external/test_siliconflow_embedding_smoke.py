"""显式启用的 SiliconFlow Embedding 付费网络 Smoke Test。"""

import os
from time import perf_counter

import httpx
import pytest

from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.tool_search.adapters.siliconflow import (
    SiliconFlowEmbeddingProvider,
)

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
        provider = SiliconFlowEmbeddingProvider(
            client,
            api_url=settings.embedding_api_url,
            api_key=SecretValue(api_key.get_secret_value()),
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_batch_size=settings.embedding_batch_size,
        )
        vectors = await provider.embed(tuple(inputs))
    assert len(vectors) == len(inputs)
    assert all(vector.dimensions == settings.embedding_dimensions for vector in vectors)
    assert all(any(value != 0 for value in vector.values) for vector in vectors)
    elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
    print(
        "SiliconFlow embedding smoke succeeded: "
        f"model={settings.embedding_model}, batch={len(vectors)}, "
        f"dimensions={settings.embedding_dimensions}, "
        f"elapsed_ms={elapsed_ms}"
    )
