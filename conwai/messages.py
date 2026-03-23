from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.storage import Storage


@dataclass
class DirectMessage:
    from_handle: str
    to_handle: str
    content: str
    timestamp: float = field(default_factory=time)


class MessageBus:
    def __init__(
        self,
        storage: Storage | None = None,
        entity: str = "WORLD",
        component: str = "messages",
    ):
        self._queues: dict[str, list[DirectMessage]] = {}
        self._known_handles: set[str] = set()
        self._storage = storage
        self._entity = entity
        self._component = component
        self._load()

    def _load(self):
        if not self._storage:
            return
        data = self._storage.load_component(self._entity, self._component)
        if data:
            self._queues = {
                k: [DirectMessage(**dm) for dm in v]
                for k, v in data.get("queues", {}).items()
            }
            self._known_handles = set(data.get("known_handles", []))

    def _save(self):
        if not self._storage:
            return
        self._storage.save_component(
            self._entity,
            self._component,
            {
                "queues": {
                    k: [
                        {
                            "from_handle": dm.from_handle,
                            "to_handle": dm.to_handle,
                            "content": dm.content,
                            "timestamp": dm.timestamp,
                        }
                        for dm in v
                    ]
                    for k, v in self._queues.items()
                },
                "known_handles": sorted(self._known_handles),
            },
        )

    def register(self, handle: str):
        self._known_handles.add(handle)
        self._save()

    def unregister(self, handle: str):
        self._known_handles.discard(handle)
        self._queues.pop(handle, None)
        self._save()

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
        self._save()
        return None

    def receive(self, handle: str) -> list[DirectMessage]:
        msgs = self._queues.pop(handle, [])
        if msgs:
            self._save()
        return msgs
