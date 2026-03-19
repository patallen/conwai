from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.app import Context

log = logging.getLogger("conwai")


class Engine:
    def __init__(self):
        self._systems: list = []

    def register(self, system) -> None:
        self._systems.append(system)
        log.info(f"[ENGINE] registered system: {system.name}")

    async def tick(self, ctx: Context) -> None:
        for system in self._systems:
            result = system.tick(ctx)
            if inspect.isawaitable(result):
                await result
