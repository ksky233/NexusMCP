"""ContextVar Log Context 的嵌套恢复与 async 隔离测试。"""

import asyncio

import pytest

from nexusmcp.shared.log_context import bind_log_context, current_log_context


def test_nested_log_context_restores_parent_values() -> None:
    assert current_log_context().request_id is None

    with bind_log_context(request_id="request-parent", tenant_id="tenant-a"):
        with bind_log_context(tool_id="tool-1"):
            context = current_log_context()
            assert context.request_id == "request-parent"
            assert context.tenant_id == "tenant-a"
            assert context.tool_id == "tool-1"

        assert current_log_context().tool_id is None
        assert current_log_context().request_id == "request-parent"

    assert current_log_context().request_id is None


@pytest.mark.asyncio
async def test_concurrent_tasks_do_not_share_log_context() -> None:
    async def capture(request_id: str) -> str | None:
        with bind_log_context(request_id=request_id):
            await asyncio.sleep(0)
            return current_log_context().request_id

    first, second = await asyncio.gather(
        capture("request-a"),
        capture("request-b"),
    )

    assert (first, second) == ("request-a", "request-b")
    assert current_log_context().request_id is None
