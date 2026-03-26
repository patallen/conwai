"""Sub-tick scheduler: perception, cognition, and action execution across sub-ticks."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Callable

from conwai.actions import ActionFeedback, ActionResult
from conwai.brain import Decision
from conwai.engine import TickNumber

if TYPE_CHECKING:
    from conwai.actions import ActionRegistry
    from conwai.brain import Brain
    from conwai.world import World

log = logging.getLogger("conwai")

# Type alias for the trigger function.
# Given an ActionResult, return a list of handles to re-trigger.
TriggerFn = Callable[[ActionResult], list[str]]


class SchedulerSystem:
    """Perceive, think, and act across sub-ticks within a single tick.

    At resolution=1, equivalent to BrainSystem followed by ActionSystem.
    At resolution>1, agents resolve at different sub-ticks based on think_cost.
    Resolved actions can trigger re-activation of idle agents at subsequent
    sub-ticks via the pluggable trigger_fn.
    """

    name = "scheduler"

    def __init__(
        self,
        brains: dict[str, Brain],
        perception: Callable,
        actions: ActionRegistry,
        resolution: int = 1,
        think_cost: int | None = None,
        retrigger_cost: int = 1,
        trigger_fn: TriggerFn | None = None,
    ):
        self.brains = brains
        self.perception = perception
        self.actions = actions
        self.resolution = max(1, resolution)
        self.think_cost = think_cost if think_cost is not None else self.resolution
        self.retrigger_cost = max(1, retrigger_cost)
        self.trigger_fn = trigger_fn

    async def run(self, world: World) -> None:
        tick = world.get_resource(TickNumber)
        entities = set(world.entities())
        handles = sorted(h for h in self.brains if h in entities)
        if not handles:
            return

        self.actions.begin_tick(world, handles)

        # Agent state: maps handle -> (asyncio.Task, resolve_subtick)
        in_flight: dict[str, tuple[asyncio.Task, int]] = {}
        idle: set[str] = set()

        # Schedule all agents to start thinking
        resolve_at = min(self.think_cost, self.resolution) - 1
        for handle in handles:
            task = asyncio.create_task(self._think(handle, world, tick.value))
            in_flight[handle] = (task, resolve_at)

        # Process sub-ticks
        for subtick in range(self.resolution):
            # Collect agents due at this sub-tick, sorted for determinism
            due_handles = sorted(
                h for h, (_, r) in in_flight.items() if r <= subtick
            )
            if not due_handles:
                continue

            # Wait for their LLM calls to finish
            due_tasks = [in_flight[h][0] for h in due_handles]
            results = await asyncio.gather(*due_tasks, return_exceptions=True)

            log.info(
                f"[SCHEDULER] subtick {subtick}/{self.resolution}: "
                f"processing {len(due_handles)} agent(s)"
            )

            # Pass 1: process all completions, move everyone to idle
            all_feedback: list[tuple[str, list[ActionResult]]] = []
            for handle, result in zip(due_handles, results):
                del in_flight[handle]

                if isinstance(result, Exception):
                    log.error(
                        f"[{handle}] scheduler error: {result}",
                        exc_info=result,
                    )
                    idle.add(handle)
                    world.set(handle, ActionFeedback(entries=[]))
                    continue

                decisions = result
                feedback = self._execute_actions(handle, decisions, world)
                world.set(handle, ActionFeedback(entries=feedback))
                idle.add(handle)
                all_feedback.append((handle, feedback))

            # Pass 2: check all triggers (order-independent)
            triggered: list[str] = []
            if self.trigger_fn and subtick + self.retrigger_cost < self.resolution:
                for _, feedback in all_feedback:
                    for entry in feedback:
                        for target in self.trigger_fn(entry):
                            if target in idle and target not in in_flight:
                                triggered.append(target)

            # Schedule re-triggered agents
            seen: set[str] = set()
            for handle in triggered:
                if handle in seen or handle in in_flight:
                    continue
                seen.add(handle)
                idle.discard(handle)
                retrigger_resolve = subtick + self.retrigger_cost
                task = asyncio.create_task(
                    self._think(handle, world, tick.value)
                )
                in_flight[handle] = (task, retrigger_resolve)
                log.info(
                    f"[{handle}] re-triggered at subtick {subtick}, "
                    f"resolves at {retrigger_resolve}"
                )

        log.info(
            f"[SCHEDULER] tick {tick.value} complete: "
            f"resolution={self.resolution}, {len(handles)} agents"
        )

    async def _think(
        self, handle: str, world: World, tick: int
    ) -> list[Decision]:
        start = time.monotonic()
        brain = self.brains[handle]
        percept = self.perception(handle, world)
        decisions = await brain.think(percept)
        world.save_raw(handle, "brain_state", brain.save_state())
        elapsed = time.monotonic() - start
        log.info(f"[{handle}] tick {tick} thought in {elapsed:.1f}s")
        return decisions

    def _execute_actions(
        self, handle: str, decisions: list[Decision], world: World
    ) -> list[ActionResult]:
        feedback_entries = []
        for decision in decisions:
            result = self.actions.execute(
                handle, decision.action, decision.args, world
            )
            feedback_entries.append(
                ActionResult(
                    action=decision.action,
                    args=decision.args,
                    result=result,
                )
            )
        return feedback_entries

    def load_brain_states(self, world: World) -> None:
        """Restore persisted brain state for all agents."""
        for handle, brain in self.brains.items():
            data = world.load_raw(handle, "brain_state")
            if data:
                brain.load_state(data)
                log.info(f"[{handle}] loaded brain state")
