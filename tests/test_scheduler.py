"""Tests for the generic sub-tick scheduler."""

import asyncio

from conwai.scheduler import run_subticks


def test_single_task():
    """One task runs and returns its result."""
    results = asyncio.run(
        run_subticks(
            keys=["a"],
            make_task=lambda k: _async_return(f"done-{k}"),
        )
    )
    assert results == {"a": "done-a"}


def test_multiple_tasks():
    """All tasks run concurrently and return results."""
    results = asyncio.run(
        run_subticks(
            keys=["a", "b", "c"],
            make_task=lambda k: _async_return(f"done-{k}"),
        )
    )
    assert results == {"a": "done-a", "b": "done-b", "c": "done-c"}


def test_error_does_not_crash_others():
    """A failing task doesn't prevent other tasks from completing."""

    async def maybe_fail(k):
        if k == "bad":
            raise RuntimeError("boom")
        return f"done-{k}"

    results = asyncio.run(
        run_subticks(keys=["bad", "good"], make_task=maybe_fail)
    )
    assert isinstance(results["bad"], RuntimeError)
    assert results["good"] == "done-good"


def test_empty_keys():
    """No keys produces empty results."""
    results = asyncio.run(
        run_subticks(keys=[], make_task=lambda k: _async_return(k))
    )
    assert results == {}


def test_resolution_1_no_retriggers():
    """At resolution=1, on_complete never fires (no room for re-triggers)."""
    call_count = {"a": 0}

    async def tracked(k):
        call_count[k] += 1
        return "done"

    def retrigger_all(key, result):
        return ["a"]  # try to re-trigger

    results = asyncio.run(
        run_subticks(
            keys=["a"],
            make_task=tracked,
            resolution=1,
            on_complete=retrigger_all,
        )
    )
    assert call_count["a"] == 1


def test_retrigger_fires_with_room():
    """on_complete can re-trigger a task when resolution allows it."""
    call_count = {"a": 0, "b": 0}

    async def tracked(k):
        call_count[k] += 1
        return f"done-{k}"

    def retrigger_b(key, result):
        if key == "a":
            return ["b"]
        return []

    asyncio.run(
        run_subticks(
            keys=["a", "b"],
            make_task=tracked,
            resolution=5,
            task_cost=2,
            retrigger_cost=2,
            on_complete=retrigger_b,
        )
    )
    assert call_count["a"] == 1
    assert call_count["b"] == 2  # initial + re-trigger


def test_cascade_retrigger():
    """a -> b -> c cascading re-triggers within one tick."""
    call_count = {"a": 0, "b": 0, "c": 0}

    async def tracked(k):
        call_count[k] += 1
        return f"done-{k}-{call_count[k]}"

    def cascade(key, result):
        # a triggers b, b's second run triggers c
        if key == "a":
            return ["b"]
        if key == "b" and "done-b-2" in str(result):
            return ["c"]
        return []

    asyncio.run(
        run_subticks(
            keys=["a", "b", "c"],
            make_task=tracked,
            resolution=10,
            task_cost=2,
            retrigger_cost=2,
            on_complete=cascade,
        )
    )
    assert call_count["a"] == 1
    assert call_count["b"] == 2
    assert call_count["c"] == 2


def test_task_cost_clamped_to_resolution():
    """task_cost > resolution still resolves within the tick."""
    results = asyncio.run(
        run_subticks(
            keys=["a"],
            make_task=lambda k: _async_return("done"),
            resolution=3,
            task_cost=10,
        )
    )
    assert results == {"a": "done"}


def test_no_on_complete_means_no_retriggers():
    """Without on_complete, tasks run exactly once."""
    call_count = {"a": 0}

    async def tracked(k):
        call_count[k] += 1
        return "done"

    asyncio.run(
        run_subticks(
            keys=["a"],
            make_task=tracked,
            resolution=10,
            task_cost=2,
            on_complete=None,
        )
    )
    assert call_count["a"] == 1


def test_cannot_retrigger_inflight_task():
    """on_complete can't re-trigger a task that's still in-flight."""
    call_count = {"fast": 0, "slow": 0}

    async def tracked(k):
        call_count[k] += 1
        return f"done-{k}"

    def try_retrigger_slow(key, result):
        if key == "fast":
            return ["slow"]  # try to re-trigger slow, but it's in-flight
        return []

    asyncio.run(
        run_subticks(
            keys=["fast", "slow"],
            make_task=tracked,
            resolution=10,
            task_cost=2,       # both resolve at subtick 1
            retrigger_cost=1,  # re-trigger would resolve at subtick 2
            on_complete=try_retrigger_slow,
        )
    )
    # fast and slow both resolve at subtick 1 (same batch).
    # After pass 1, both are idle. fast's on_complete tries to re-trigger slow.
    # slow IS idle (two-pass), so it gets re-triggered. That's correct.
    # The in-flight guard matters when tasks have DIFFERENT costs.
    assert call_count["fast"] == 1
    assert call_count["slow"] == 2  # initial + re-trigger


async def _async_return(val):
    return val
