from dataclasses import dataclass, field
from time import time


@dataclass
class DirectMessage:
    from_handle: str
    to_handle: str
    content: str
    timestamp: float = field(default_factory=time)


class MessageBus:
    def __init__(self):
        self._queues: dict[str, list[DirectMessage]] = {}
        self._known_handles: set[str] = set()

    def register(self, handle: str):
        self._known_handles.add(handle)

    def send(self, from_handle: str, to_handle: str, content: str) -> str | None:
        if from_handle == to_handle:
            return "Cannot message yourself."
        if to_handle not in self._known_handles:
            return f"Unknown handle: {to_handle}. Message not delivered."
        if to_handle not in self._queues:
            self._queues[to_handle] = []
        self._queues[to_handle].append(
            DirectMessage(from_handle=from_handle, to_handle=to_handle, content=content)
        )
        return None

    def receive(self, handle: str) -> list[DirectMessage]:
        msgs = self._queues.pop(handle, [])
        return msgs

    def format_new(self, handle: str) -> str | None:
        msgs = self.receive(handle)
        if not msgs:
            return None
        lines = [f"DM from {m.from_handle}: {m.content}" for m in msgs]
        return "\n\n".join(lines)
