"""Toolset Domain 的类型化业务冲突。"""


class ToolsetDomainError(ValueError):
    """可由 Application Layer 稳定映射的领域拒绝。"""


class ToolsetRevisionConflict(ToolsetDomainError):
    """Aggregate 已不再处于调用方观察到的 Revision。"""


class SystemToolsetMutationError(ToolsetDomainError):
    """操作试图修改系统 Toolset 的受保护结构。"""
