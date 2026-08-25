"""Clock Port 的系统时间 Adapter。"""

from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
