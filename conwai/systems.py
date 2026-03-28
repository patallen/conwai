"""Reusable system implementations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from conwai.actions import ActionFeedback, ActionResult, PendingActions

if TYPE_CHECKING:
    from conwai.actions import ActionRegistry
    from conwai.world import World


log = logging.getLogger("conwai")


class ActionSystem:
    """Execute pending actions and write feedback."""

    name = "actions"

    def __init__(self, actions: ActionRegistry):
        self.actions = actions

    async def run(self, world: World) -> None:
        pending_pairs = list(world.query(PendingActions))
        self.actions.begin_tick(world, [eid for eid, _ in pending_pairs])

        for entity_id, pending in pending_pairs:
            feedback_entries = []
            for decision in pending.entries:
                result = self.actions.execute(
                    entity_id, decision.action, decision.args, world
                )
                feedback_entries.append(
                    ActionResult(
                        action=decision.action,
                        args=decision.args,
                        result=result,
                    )
                )
            world.set(entity_id, ActionFeedback(entries=feedback_entries))
            pending.entries.clear()
