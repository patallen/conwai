"""Typed component base class for the entity-component store."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields
from typing import ClassVar, Self


@dataclass
class Component:
    """Base class for typed components.

    Subclass this to define scenario-specific state that gets stored per agent.
    The component name is derived from the class name (CamelCase → snake_case)
    unless overridden via ``__component_name__``.

    Example::

        @dataclass
        class Inventory(Component):
            flour: int = 0
            water: int = 0

        store.register(Inventory)
        store.get(handle, Inventory)  # → Inventory(flour=0, water=0)
    """

    __component_name__: ClassVar[str] = ""

    @classmethod
    def component_name(cls) -> str:
        if cls.__component_name__:
            return cls.__component_name__
        return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})
