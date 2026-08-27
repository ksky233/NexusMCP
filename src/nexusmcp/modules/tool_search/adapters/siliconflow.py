"""SiliconFlow Qwen EmbeddingProvider HTTP Adapter。"""

from collections.abc import Mapping
from typing import Any

import httpx

from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.tool_search.domain import EmbeddingVector
from nexusmcp.shared.errors import (
    EmbeddingAuthenticationError,
    EmbeddingRateLimitError,
    EmbeddingResponseError,
    EmbeddingUnavailableError,
)


class SiliconFlowEmbeddingProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_url: str,
        api_key: SecretValue,
        model: str,
        dimensions: int,
        timeout_seconds: float = 60.0,
        max_batch_size: int = 64,
    ) -> None:
        if not api_url.startswith(("https://", "http://")):
            raise ValueError("embedding API URL must use http or https")
        if not model.strip():
            raise ValueError("embedding model must not be blank")
        if dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")
        if timeout_seconds <= 0:
            raise ValueError("embedding timeout must be positive")
        if max_batch_size <= 0:
            raise ValueError("embedding max batch size must be positive")
        self._client = client
        self._api_url = api_url
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        self._max_batch_size = max_batch_size

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        if not texts or len(texts) > self._max_batch_size:
            raise ValueError("embedding batch size was invalid")
        if any(not text.strip() for text in texts):
            raise ValueError("embedding text must not be blank")
        try:
            response = await self._client.post(
                self._api_url,
                headers={"Authorization": f"Bearer {self._api_key.reveal()}"},
                json={
                    "model": self._model,
                    "input": list(texts),
                    "encoding_format": "float",
                    "dimensions": self._dimensions,
                },
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException:
            raise EmbeddingUnavailableError("embedding provider timed out") from None
        except httpx.NetworkError:
            raise EmbeddingUnavailableError("embedding provider network failure") from None
        if response.status_code in {401, 403}:
            raise EmbeddingAuthenticationError("embedding provider rejected credential")
        if response.status_code == 429:
            raise EmbeddingRateLimitError("embedding provider returned rate limit")
        if response.status_code >= 500:
            raise EmbeddingUnavailableError(
                f"embedding provider returned HTTP {response.status_code}"
            )
        if response.status_code != 200:
            raise EmbeddingResponseError(f"embedding provider returned HTTP {response.status_code}")
        try:
            payload: Any = response.json()
        except ValueError:
            raise EmbeddingResponseError("embedding response was not JSON") from None
        return self._parse_vectors(payload, expected_count=len(texts))

    def _parse_vectors(
        self,
        payload: object,
        *,
        expected_count: int,
    ) -> tuple[EmbeddingVector, ...]:
        if not isinstance(payload, Mapping):
            raise EmbeddingResponseError("embedding response root was not an object")
        raw_data = payload.get("data")
        if not isinstance(raw_data, list) or len(raw_data) != expected_count:
            raise EmbeddingResponseError("embedding response count did not match request")
        by_index: dict[int, EmbeddingVector] = {}
        for raw_item in raw_data:
            if not isinstance(raw_item, Mapping):
                raise EmbeddingResponseError("embedding response item was invalid")
            index = raw_item.get("index")
            raw_vector = raw_item.get("embedding")
            if isinstance(index, bool) or not isinstance(index, int):
                raise EmbeddingResponseError("embedding response index was invalid")
            if not isinstance(raw_vector, list):
                raise EmbeddingResponseError("embedding response vector was invalid")
            values: list[float] = []
            for value in raw_vector:
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise EmbeddingResponseError("embedding response contained non-numeric value")
                values.append(float(value))
            try:
                vector = EmbeddingVector(
                    model=self._model,
                    dimensions=self._dimensions,
                    values=tuple(values),
                )
            except ValueError as error:
                raise EmbeddingResponseError("embedding vector validation failed") from error
            if index in by_index:
                raise EmbeddingResponseError("embedding response index was duplicated")
            by_index[index] = vector
        if set(by_index) != set(range(expected_count)):
            raise EmbeddingResponseError("embedding response indices were incomplete")
        return tuple(by_index[index] for index in range(expected_count))
