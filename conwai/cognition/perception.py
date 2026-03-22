from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from conwai.cognition.percept import ActionFeedback

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.messages import MessageBus
    from conwai.store import ComponentStore
    from conwai.typemap import Percept


class PerceptionBuilder(Protocol):
    """What the engine needs from a perception system."""

    def build(
        self,
        agent: Agent,
        store: ComponentStore,
        board: BulletinBoard,
        bus: MessageBus,
        tick: int,
        action_feedback: list[ActionFeedback] | None = None,
    ) -> Percept: ...

    def notify(self, handle: str, message: str) -> None: ...

    def build_system_prompt(self) -> str: ...
