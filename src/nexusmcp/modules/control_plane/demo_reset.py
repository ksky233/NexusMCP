"""公开演示环境的工作区重置契约与 Use Case。"""

from dataclasses import dataclass
from typing import Protocol

from nexusmcp.shared.request_context import ActorContext


class DemoWorkspaceResetter(Protocol):
    """清理单 Tenant 演示状态并恢复可继续操作的最小基线。"""

    async def reset(self, tenant_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class DemoWorkspaceResetResult:
    tenant_id: str


class ResetDemoWorkspace:
    """显式表达 Demo-only 破坏性操作，不把它伪装成普通 Repository 方法。"""

    def __init__(self, resetter: DemoWorkspaceResetter) -> None:
        self._resetter = resetter

    async def execute(self, context: ActorContext) -> DemoWorkspaceResetResult:
        await self._resetter.reset(context.tenant_id)
        return DemoWorkspaceResetResult(tenant_id=context.tenant_id)
