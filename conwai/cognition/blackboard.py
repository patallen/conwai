from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from conwai.cognition.brain import Decision
from conwai.cognition.percept import Percept

if TYPE_CHECKING:
    from conwai.store import ComponentStore


class Process(Protocol):
    async def run(self, board: dict[str, Any]) -> None: ...


class BlackboardBrain:
    """Composable brain that runs a pipeline of processes on a shared board.

    The board is a transactional workspace: initialized from the percept and
    any persistent brain state in the component store, mutated by processes,
    then committed back after think() completes.
    """

    def __init__(
        self,
        processes: list[Process],
        store: ComponentStore | None = None,
        component: str = "brain",
    ):
        self.processes = processes
        self.store = store
        self.component = component

    async def think(self, percept: Percept) -> list[Decision]:
        board: dict[str, Any] = {"percept": percept, "decisions": []}

        if self.store and self.store.has(percept.agent_id, self.component):
            state = self.store.get(percept.agent_id, self.component)
            board["state"] = state

        for process in self.processes:
            await process.run(board)

        decisions: list[Decision] = board.get("decisions", [])

        if self.store:
            state = board.get("state", {})
            self.store.set(percept.agent_id, self.component, state)

        return decisions
