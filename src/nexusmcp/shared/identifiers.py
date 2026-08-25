"""需要可测试 ID 生成的 Use Case 所依赖的 Port。"""

from typing import Protocol


class IdentifierGenerator(Protocol):
    def new_id(self) -> str: ...
