"""只允许受控 Root 内 JSON Fixture 的 OpenAPI Document Reader。"""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from nexusmcp.modules.openapi_import.domain import OpenApiDocument
from nexusmcp.shared.errors import OpenApiDocumentInvalidError, OpenApiSourceNotFoundError


class LocalOpenApiDocumentReader:
    def __init__(self, allowed_root: Path, *, max_bytes: int = 1_048_576) -> None:
        if max_bytes <= 0:
            raise ValueError("OpenAPI document max bytes must be positive")
        self._allowed_root = allowed_root.resolve()
        self._max_bytes = max_bytes

    async def read(self, source_ref: str) -> OpenApiDocument:
        source_path = (self._allowed_root / source_ref).resolve()
        if not source_path.is_relative_to(self._allowed_root):
            raise OpenApiSourceNotFoundError("local fixture escaped the allowed root")
        if source_path.suffix.lower() != ".json":
            raise OpenApiDocumentInvalidError("only JSON local fixtures are enabled")
        try:
            stat = await asyncio.to_thread(source_path.stat)
            if stat.st_size > self._max_bytes:
                raise OpenApiDocumentInvalidError("OpenAPI document exceeded size limit")
            raw_content = await asyncio.to_thread(source_path.read_bytes)
        except FileNotFoundError:
            raise OpenApiSourceNotFoundError(
                f"OpenAPI fixture {source_ref} was not found"
            ) from None
        try:
            parsed: Any = json.loads(raw_content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise OpenApiDocumentInvalidError("OpenAPI fixture is not valid UTF-8 JSON") from None
        if not isinstance(parsed, dict):
            raise OpenApiDocumentInvalidError("OpenAPI document root must be an object")
        return OpenApiDocument(
            source_ref=source_ref,
            source_digest=hashlib.sha256(raw_content).hexdigest(),
            content=parsed,
        )
