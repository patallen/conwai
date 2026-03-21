from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext


def make_world_handlers(world_events=None):
    """Return (_submit_code, _vote) handler functions that delegate to world_events."""

    def _submit_code(agent: Agent, ctx: TickContext, args: dict) -> str:
        if world_events is None:
            return "No active code challenge."
        guess = args.get("code", "")
        return world_events.submit_code(agent, guess)

    def _vote(agent: Agent, ctx: TickContext, args: dict) -> str:
        if world_events is None:
            return "No active election."
        candidate = args.get("candidate", "").lstrip("@")
        return world_events.cast_vote(agent, candidate)

    return _submit_code, _vote
