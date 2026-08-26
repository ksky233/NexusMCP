"""Retry Backoff 使用的 asyncio Sleeper。"""

import asyncio


class AsyncioRetrySleeper:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
