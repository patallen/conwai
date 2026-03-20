from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.messages import MessageBus
    from conwai.store import ComponentStore


class Perception:
    def __init__(
        self,
        identity_builder: Callable,
        tick_builder: Callable,
        system_prompt: str,
    ):
        self._notifications: dict[str, list[str]] = defaultdict(list)
        self._identity_builder = identity_builder
        self._tick_builder = tick_builder
        self._system_prompt = system_prompt

    def notify(self, handle: str, message: str) -> None:
        self._notifications[handle].append(message)

    def drain_notifications(self, handle: str) -> list[str]:
        return self._notifications.pop(handle, [])

    def build_system_prompt(self) -> str:
        return self._system_prompt

    def build_identity(self, agent: Agent, store: ComponentStore) -> str:
        return self._identity_builder(agent, store)

    def build(
        self,
        agent: Agent,
        store: ComponentStore,
        board: BulletinBoard,
        bus: MessageBus,
        tick: int,
    ) -> str:
        notifications = self.drain_notifications(agent.handle)
        return self._tick_builder(agent, store, board, bus, tick, notifications)
