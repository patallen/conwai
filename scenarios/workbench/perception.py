from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from conwai.cognition.percept import ActionFeedback

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.messages import MessageBus
    from conwai.store import ComponentStore


@dataclass
class WorkbenchPercept:
    agent_id: str
    tick: int
    identity: str
    prompt_text: str
    action_feedback: list[ActionFeedback] = field(default_factory=list)

    def to_prompt(self) -> str:
        return self.prompt_text


class WorkbenchPerceptionBuilder:
    """Builds percepts from broadcasts, DMs, and injected stimuli."""

    def __init__(self):
        self._stimuli: dict[str, list[str]] = {}

    def inject(self, handle: str, text: str) -> None:
        """Inject a stimulus that will appear in the agent's next percept."""
        self._stimuli.setdefault(handle, []).append(text)

    def notify(self, handle: str, message: str) -> None:
        """Alias for inject, satisfies PerceptionBuilder protocol."""
        self.inject(handle, message)

    def build_system_prompt(self) -> str:
        return (
            "You are an agent in a shared environment with other agents. "
            "Communicate, observe, and act. Keep responses concise: state your "
            "decision and reasoning in 1-2 sentences, then act."
        )

    def build(
        self,
        agent: Agent,
        store: ComponentStore,
        board: BulletinBoard | None = None,
        bus: MessageBus | None = None,
        tick: int = 0,
        action_feedback: list[ActionFeedback] | None = None,
    ) -> WorkbenchPercept:
        info = store.get(agent.handle, "agent_info")

        identity = (
            f"You are @{agent.handle}. "
            f"Your temperament is {info['personality']} — this is innate."
        )
        if info.get("role"):
            identity += f" Your role: {info['role']}."

        parts = []

        if board:
            new_posts = board.read_new(agent.handle)
            if new_posts:
                parts.append(
                    "Broadcast:\n"
                    + "\n".join(f"@{p.handle}: {p.content}" for p in new_posts)
                )

        if bus:
            new_dms = bus.receive(agent.handle)
            if new_dms:
                parts.append(
                    "\n".join(
                        f"DM from @{dm.from_handle}: {dm.content}" for dm in new_dms
                    )
                )

        stimuli = self._stimuli.pop(agent.handle, [])
        if stimuli:
            parts.extend(stimuli)

        if not parts:
            parts.append("Nothing new has happened.")

        prompt_text = "\n\n".join(parts)

        return WorkbenchPercept(
            agent_id=agent.handle,
            tick=tick,
            identity=identity,
            prompt_text=prompt_text,
            action_feedback=action_feedback or [],
        )
