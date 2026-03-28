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


class State(_TypeMap):
    """Persistent typed state that carries across cognitive cycles.

    Processes read and write typed entries via BrainContext.state.
    The Brain serializes/deserializes this for persistence between ticks.
    """

    def set[T](self, val: T) -> None:
        """Store a value, keyed by its type."""
        self._data[type(val)] = val

    def remove(self, key: type) -> None:
        """Remove a value by type."""
        self._data.pop(key, None)

    def serialize(self) -> dict:
        """Serialize all entries to a dict keyed by class name."""
        from dataclasses import asdict

        return {
            type(val).__name__: asdict(val)  # type: ignore[call-overload]
            for val in self._data.values()
            if hasattr(val, "__dataclass_fields__")
        }

    @classmethod
    def deserialize(cls, data: dict, type_registry: dict[str, type]) -> State:
        """Deserialize from a dict using a type registry for reconstruction."""
        state = cls()
        for name, fields in data.items():
            typ = type_registry.get(name)
            if typ is None:
                continue
            if hasattr(typ, "from_dict"):
                state.set(typ.from_dict(fields))
            else:
                state.set(typ(**fields))
        return state


class Blackboard(_TypeMap):
    """Per-cycle scratch workspace for inter-process communication.

    Created fresh each think() cycle. Processes read and write typed
    entries (Decisions, LLMSnapshot, RecalledMemories) that are
    discarded at the end of the cycle. Persistent state lives on State.

    Example::

        bb = Blackboard()
        bb.set(LLMSnapshot(messages=[...]))
        snap = bb.get(LLMSnapshot)  # typed as LLMSnapshot | None
    """

    def set[T](self, val: T) -> None:
        """Store a value, keyed by its type."""
        self._data[type(val)] = val

    def remove(self, key: type) -> None:
        """Remove a value by type."""
        self._data.pop(key, None)
