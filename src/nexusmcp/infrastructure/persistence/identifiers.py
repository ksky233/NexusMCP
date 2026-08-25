"""Persistence Adapter 使用的 UUID 边界转换。"""

import uuid


def as_uuid(value: str, *, field_name: str) -> uuid.UUID:
    """在 ORM 边界解析 UUID，不把存储类型扩散到 Domain Port。"""

    try:
        return uuid.UUID(value)
    except ValueError:
        raise ValueError(f"{field_name} must be a valid UUID") from None
