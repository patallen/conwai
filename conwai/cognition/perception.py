from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from conwai.cognition.percept import ActionFeedback

if TYPE_CHECKING:
    from conwai.typemap import Percept
    from conwai.world import World


class PerceptionBuilder(Protocol):
    """What the engine needs from a perception system."""

    def build(
        self,
        entity_id: str,
        world: World,
        action_feedback: list[ActionFeedback] | None = None,
    ) -> Percept: ...

    def notify(self, handle: str, message: str) -> None: ...

    def build_system_prompt(self) -> str: ...
