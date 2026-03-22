from __future__ import annotations

from typing import TYPE_CHECKING

from conwai.bulletin_board import BulletinBoard
from conwai.cognition.percept import ActionFeedback
from conwai.engine import TickNumber
from conwai.messages import MessageBus
from conwai.processes.types import AgentHandle, Identity, Observations, PerceptFeedback
from conwai.processes.types import TickNumber as PerceptTickNumber
from conwai.typemap import Percept
from scenarios.workbench.components import AgentInfo

if TYPE_CHECKING:
    from conwai.world import World


class WorkbenchPerceptionBuilder:
    """Builds percepts from broadcasts, DMs, and injected stimuli."""

    def __init__(self):
        self._stimuli: dict[str, list[str]] = {}

    def inject(self, handle: str, text: str) -> None:
        self._stimuli.setdefault(handle, []).append(text)

    def notify(self, handle: str, message: str) -> None:
        self.inject(handle, message)

    def build_system_prompt(self) -> str:
        return (
            "You are an agent in a shared environment with other agents. "
            "Communicate, observe, and act. Keep responses concise: state your "
            "decision and reasoning in 1-2 sentences, then act."
        )

    def build(
        self,
        entity_id: str,
        world: World,
        action_feedback: list[ActionFeedback] | None = None,
    ) -> Percept:
        tick = world.get_resource(TickNumber).value
        board = world.get_resource(BulletinBoard)
        bus = world.get_resource(MessageBus)

        info = world.get(entity_id, AgentInfo)

        identity = (
            f"You are @{entity_id}. "
            f"Your temperament is {info.personality} — this is innate."
        )
        if info.role:
            identity += f" Your role: {info.role}."

        parts = []

        new_posts = board.read_new(entity_id)
        if new_posts:
            parts.append(
                "Broadcast:\n"
                + "\n".join(f"@{p.handle}: {p.content}" for p in new_posts)
            )

        new_dms = bus.receive(entity_id)
        if new_dms:
            parts.append(
                "\n".join(
                    f"DM from @{dm.from_handle}: {dm.content}" for dm in new_dms
                )
            )

        stimuli = self._stimuli.pop(entity_id, [])
        if stimuli:
            parts.extend(stimuli)

        if not parts:
            parts.append("Nothing new has happened.")

        observations = "\n\n".join(parts)

        percept = Percept()
        percept.set(AgentHandle(value=entity_id))
        percept.set(PerceptTickNumber(value=tick))
        percept.set(Identity(text=identity))
        percept.set(Observations(text=observations))
        percept.set(PerceptFeedback(entries=action_feedback or []))
        return percept
