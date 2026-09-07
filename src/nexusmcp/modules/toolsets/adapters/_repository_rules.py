"""Toolset Repository Adapter 共享的保存边界。"""

from nexusmcp.modules.toolsets.domain import Toolset


def requires_persistence_update(current: Toolset, replacement: Toolset) -> bool:
    """验证替换来自一次合法领域变更，并识别幂等重复保存。"""
    if (
        current.id != replacement.id
        or current.tenant_id != replacement.tenant_id
        or current.slug != replacement.slug
        or current.kind is not replacement.kind
        or current.created_by != replacement.created_by
        or current.created_at != replacement.created_at
    ):
        raise ValueError("toolset stable identity fields are immutable")
    if replacement == current:
        return False
    if replacement.revision != current.revision + 1:
        raise ValueError("toolset revision transition was invalid")
    return True
