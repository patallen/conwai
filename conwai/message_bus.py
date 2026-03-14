import asyncio
from typing import Callable, Awaitable


class MessageBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable[..., Awaitable]]] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self.running = False

    def on(self, event_type: str, handler: Callable[..., Awaitable]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def emit(self, event_type: str, data: dict | None = None) -> None:
        await self._queue.put((event_type, data or {}))

    async def run(self):
        self.running = True
        while self.running:
            event_type, data = await self._queue.get()
            handlers = self._handlers.get(event_type, [])
            await asyncio.gather(*(h(data) for h in handlers))

    def stop(self):
        self.running = False
