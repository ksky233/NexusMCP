"""OpenAPI 文档读取与解析 Port。"""

from typing import Protocol

from nexusmcp.modules.openapi_import.domain import OpenApiDocument


class OpenApiDocumentReader(Protocol):
    async def read(self, source_ref: str) -> OpenApiDocument: ...
