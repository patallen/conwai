"""Generic sub-tick scheduler for async work within a simulation tick."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

log = logging.getLogger("conwai")

# task_fn: async () -> result
TaskFn = Callable[[], Awaitable[Any]]

# on_complete: (key, result) -> list of keys to re-schedule
OnComplete = Callable[[str, Any], list[str]]


async def run_subticks(
    keys: list[str],
    make_task: Callable[[str], Awaitable[Any]],
    resolution: int = 1,
    task_cost: int | None = None,
    retrigger_cost: int = 1,
    on_complete: OnComplete | None = None,
) -> dict[str, Any]:
    """Run async tasks across sub-ticks.

    Args:
        keys: Initial work items to schedule.
        make_task: Called with a key, returns an awaitable that produces a result.
        resolution: Number of sub-ticks per tick.
        task_cost: Sub-ticks until a task resolves. Defaults to resolution.
        retrigger_cost: Sub-ticks until a re-triggered task resolves.
        on_complete: Called after each task completes with (key, result).
            Returns list of keys to re-schedule. Only called when there are
            enough sub-ticks remaining for the re-triggered work to resolve.

    Returns:
        Dict mapping each key to its result (or Exception if it failed).
    """
    resolution = max(1, resolution)
    task_cost = task_cost if task_cost is not None else resolution
    retrigger_cost = max(1, retrigger_cost)

    # key -> (asyncio.Task, resolve_subtick)
    in_flight: dict[str, tuple[asyncio.Task, int]] = {}
    idle: set[str] = set()
    all_results: dict[str, Any] = {}

    # Schedule initial tasks
    resolve_at = min(task_cost, resolution) - 1
    for key in keys:
        task = asyncio.create_task(make_task(key))
        in_flight[key] = (task, resolve_at)

    for subtick in range(resolution):
        due_keys = sorted(k for k, (_, r) in in_flight.items() if r <= subtick)
        if not due_keys:
            continue

        due_tasks = [in_flight[k][0] for k in due_keys]
        results = await asyncio.gather(*due_tasks, return_exceptions=True)

        log.info(
            f"[SCHEDULER] subtick {subtick}/{resolution}: "
            f"processing {len(due_keys)} task(s)"
        )

        # Pass 1: collect all results
        completed: list[tuple[str, Any]] = []
        for key, result in zip(due_keys, results):
            del in_flight[key]
            idle.add(key)
            all_results[key] = result

            if isinstance(result, Exception):
                log.error(f"[SCHEDULER] {key} error: {result}", exc_info=result)
            else:
                completed.append((key, result))

        # Pass 2: check re-triggers (order-independent)
        triggered: list[str] = []
        if on_complete and subtick + retrigger_cost < resolution:
            for key, result in completed:
                for target in on_complete(key, result):
                    if target in idle and target not in in_flight:
                        triggered.append(target)

        # Schedule re-triggered tasks
        seen: set[str] = set()
        for key in triggered:
            if key in seen or key in in_flight:
                continue
            seen.add(key)
            idle.discard(key)
            task = asyncio.create_task(make_task(key))
            in_flight[key] = (task, subtick + retrigger_cost)
            log.info(
                f"[SCHEDULER] {key} re-triggered at subtick {subtick}, "
                f"resolves at {subtick + retrigger_cost}"
            )

    log.info(f"[SCHEDULER] complete: resolution={resolution}, {len(keys)} tasks")
    return all_results
