"""Catalog 生命周期产生、由事务外消费者处理的 Domain Event。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ToolPublished:
    tenant_id: str
    tool_id: str
    tool_version_id: str
    tool_binding_id: str
    canonical_name: str
    version: int
    actor_id: str
    request_id: str
    trace_id: str
    occurred_at: datetime
