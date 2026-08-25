"""Local Fixture Reader 的 Root、格式和大小安全边界测试。"""

from pathlib import Path

import pytest

from nexusmcp.modules.openapi_import.adapters.local_document_reader import (
    LocalOpenApiDocumentReader,
)
from nexusmcp.shared.errors import OpenApiDocumentInvalidError, OpenApiSourceNotFoundError


@pytest.mark.asyncio
async def test_reader_rejects_path_traversal(tmp_path: Path) -> None:
    reader = LocalOpenApiDocumentReader(tmp_path / "allowed")

    with pytest.raises(OpenApiSourceNotFoundError):
        await reader.read("../outside.json")


@pytest.mark.asyncio
async def test_reader_rejects_non_object_and_oversized_json(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "array.json").write_text("[]", encoding="utf-8")
    (allowed / "large.json").write_text('{"openapi":"3.1.0"}', encoding="utf-8")

    with pytest.raises(OpenApiDocumentInvalidError, match="root"):
        await LocalOpenApiDocumentReader(allowed).read("array.json")
    with pytest.raises(OpenApiDocumentInvalidError, match="size"):
        await LocalOpenApiDocumentReader(allowed, max_bytes=4).read("large.json")
