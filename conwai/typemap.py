"""Typesafe heterogeneous containers for the cognitive pipeline.

Built on the same pattern as Rust's http::Extensions and Java's Effective
Java Item 33 (typesafe heterogeneous containers). The value's type is the key.
"""

from __future__ import annotations


class _TypeMap:
    """Base type-keyed heterogeneous container."""

    __slots__ = ("_data",)

    def __init__(self) -> None:
        self._data: dict[type, object] = {}

    def get[T](self, key: type[T]) -> T | None:
        """Retrieve a value by type, or None if not present."""
        return self._data.get(key)  # type: ignore[return-value]

    def has(self, key: type) -> bool:
        """Check if a value of the given type is stored."""
        return key in self._data

    def __repr__(self) -> str:
        types = ", ".join(t.__name__ for t in self._data)
        return f"{type(self).__name__}({types})"


class Percept(_TypeMap):
    """Read-only typed entries from the scenario — what the agent perceives.

    The scenario's perception builder populates a Percept with typed entries
    (Identity, Observations, etc.). Processes can read them but not mutate.

    Example::

        percept = Percept()
        percept.set(Identity(text="You are @Alice"))
        percept.set(Observations(text="Board: @Bob sold flour"))
        # now read-only when passed to processes
    """

    def set[T](self, val: T) -> None:
        """Store a value. Called by the perception builder during construction."""
        self._data[type(val)] = val


class Blackboard(_TypeMap):
    """Mutable typed workspace for inter-process communication.

    Processes read and write typed entries during a cognitive cycle.
    The blackboard persists on the brain instance across cycles —
    working memory and episodes accumulate over time.

    Example::

        bb = Blackboard()
        bb.set(WorkingMemory(entries=[...]))
        wm = bb.get(WorkingMemory)  # typed as WorkingMemory | None
    """

    def set[T](self, val: T) -> None:
        """Store a value, keyed by its type."""
        self._data[type(val)] = val

    def remove(self, key: type) -> None:
        """Remove a value by type."""
        self._data.pop(key, None)
