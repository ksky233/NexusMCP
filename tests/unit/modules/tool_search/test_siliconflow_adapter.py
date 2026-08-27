"""SiliconFlow Adapter 的 Batch 顺序、维度和安全错误测试。"""

import httpx
import pytest

from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.tool_search.adapters.siliconflow import (
    SiliconFlowEmbeddingProvider,
)
from nexusmcp.shared.errors import EmbeddingRateLimitError, EmbeddingResponseError


def provider(
    handler: httpx.MockTransport,
    *,
    api_key: str = "smoke-secret-key",
) -> tuple[SiliconFlowEmbeddingProvider, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=handler)
    return (
        SiliconFlowEmbeddingProvider(
            client,
            api_url="https://embedding.test/v1/embeddings",
            api_key=SecretValue(api_key),
            model="test/embedding",
            dimensions=3,
        ),
        client,
    )


@pytest.mark.asyncio
async def test_adapter_preserves_batch_order_and_never_echoes_secret() -> None:
    captured_authorization = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_authorization
        captured_authorization = request.headers["Authorization"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ]
            },
        )

    adapter, client = provider(httpx.MockTransport(handler))
    try:
        vectors = await adapter.embed(("first", "second"))
    finally:
        await client.aclose()

    assert vectors[0].values == (1.0, 0.0, 0.0)
    assert vectors[1].values == (0.0, 1.0, 0.0)
    assert captured_authorization == "Bearer smoke-secret-key"
    assert "smoke-secret-key" not in repr(adapter)


@pytest.mark.asyncio
async def test_adapter_normalizes_rate_limit_without_response_body() -> None:
    adapter, client = provider(
        httpx.MockTransport(lambda _request: httpx.Response(429, text="internal quota detail"))
    )
    try:
        with pytest.raises(EmbeddingRateLimitError) as captured:
            await adapter.embed(("one",))
    finally:
        await client.aclose()

    assert "internal quota detail" not in str(captured.value)


@pytest.mark.asyncio
async def test_adapter_rejects_wrong_dimensions_and_non_finite_values() -> None:
    responses = iter(
        [
            httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]}),
            httpx.Response(
                200,
                content=b'{"data":[{"index":0,"embedding":[1.0,NaN,0.0]}]}',
                headers={"Content-Type": "application/json"},
            ),
        ]
    )
    adapter, client = provider(httpx.MockTransport(lambda _request: next(responses)))
    try:
        with pytest.raises(EmbeddingResponseError):
            await adapter.embed(("wrong dimensions",))
        with pytest.raises(EmbeddingResponseError):
            await adapter.embed(("not finite",))
    finally:
        await client.aclose()
