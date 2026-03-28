"""Brain: a cognitive pipeline over a persistent state and per-cycle blackboard."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import structlog

from conwai.typemap import Blackboard, Percept, State

log = structlog.get_logger()


@dataclass
class Decision:
    action: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decisions:
    """Actions the agent wants to take this cycle."""

    entries: list[Decision] = field(default_factory=list)


@dataclass
class BrainContext:
    """Everything a process needs for one cognitive cycle."""

    percept: Percept
    state: State
    bb: Blackboard


class Process(Protocol):
    async def run(self, ctx: BrainContext) -> None: ...


@runtime_checkable
class ActionAdapter(Protocol):
    """Bridge between cognition and environment. Like ACT-R's motor module."""

    async def execute(self, handle: str, decisions: list[Decision]) -> list: ...


@runtime_checkable
class Brain(Protocol):
    """Framework-level brain interface. Concrete brains implement this."""

    def perceive(self, percept: Percept, scheduler: Any, handle: str) -> None: ...
    def save_state(self) -> dict: ...
    def load_state(self, data: dict) -> None: ...


class PipelineBrain:
    """Run a pipeline of processes, producing decisions.

    Implements the Brain protocol by scheduling the full pipeline as a
    single task on the Scheduler. The adapter handles action execution
    after the pipeline completes.
    """

    def __init__(
        self,
        processes: list[Process],
        adapter: ActionAdapter,
        state_types: list[type] | None = None,
    ):
        self.processes = processes
        self.adapter = adapter
        self.state = State()
        self._state_registry = {t.__name__: t for t in (state_types or [])}
        self._last_snapshot: dict | None = None

    def perceive(self, percept: Percept, scheduler: Any, handle: str) -> None:
        async def run_pipeline():
            ctx = BrainContext(percept=percept, state=self.state, bb=Blackboard())

            for process in self.processes:
                t0 = time.monotonic()
                await process.run(ctx)
                log.debug(
                    "process_complete",
                    handle=handle,
                    process=process.__class__.__name__,
                    elapsed_s=round(time.monotonic() - t0, 3),
                )

            from conwai.processes.types import LLMSnapshot

            snap = ctx.bb.get(LLMSnapshot)
            if snap:
                self._last_snapshot = {
                    "system": snap.system_prompt,
                    "messages": snap.messages,
                }

            decisions_obj = ctx.bb.get(Decisions)
            if decisions_obj and decisions_obj.entries:
                await self.adapter.execute(handle, decisions_obj.entries)
                log.info(
                    "pipeline_complete",
                    handle=handle,
                    decisions=len(decisions_obj.entries),
                )
            else:
                log.debug("pipeline_complete", handle=handle, decisions=0)

        scheduler.schedule(f"{handle}:think", run_pipeline)

    def save_state(self) -> dict:
        """Serialize persistent state for storage."""
        data = self.state.serialize()
        if self._last_snapshot:
            data["_llm_snapshot"] = self._last_snapshot
        return data

    def load_state(self, data: dict) -> None:
        """Restore persistent state from storage."""
        self.state = State.deserialize(data, self._state_registry)
