from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from conwai.app import Context

log = logging.getLogger("conwai")


@runtime_checkable
class System(Protocol):
    name: str

    def tick(self, ctx: Context) -> None: ...


class Engine:
    def __init__(self):
        self._systems: list[System] = []

    def register(self, system: System) -> None:
        self._systems.append(system)
        log.info(f"[ENGINE] registered system: {system.name}")

    def tick(self, ctx: Context) -> None:
        for system in self._systems:
            system.tick(ctx)
