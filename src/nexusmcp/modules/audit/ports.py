"""Audit 追加写入 Port。"""

from typing import Protocol

from nexusmcp.modules.audit.domain import AuditEvent


class AuditSink(Protocol):
    async def append(self, event: AuditEvent) -> None: ...
