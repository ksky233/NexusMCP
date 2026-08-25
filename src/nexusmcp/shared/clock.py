"""需要可测试时间的 Use Case 所依赖的 Clock Port。"""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
