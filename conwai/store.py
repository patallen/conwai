from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from conwai.component import Component

if TYPE_CHECKING:
    from conwai.storage import Storage


class ComponentStore:
    def __init__(self, storage: Storage | None = None):
        self._defaults: dict[str, Component] = {}  # name -> default instance
        self._types: dict[str, type[Component]] = {}  # name -> component class
        self._data: dict[str, dict[str, Component]] = {}  # handle -> name -> instance
        self._storage = storage

    # -- Registration -------------------------------------------------------

    def register[T: Component](self, component_type: type[T], defaults: T | None = None) -> None:
        name = component_type.component_name()
        self._types[name] = component_type
        self._defaults[name] = defaults if defaults is not None else component_type()

    # -- Agent lifecycle ----------------------------------------------------

    def init_agent(self, handle: str, overrides: list[Component] | None = None) -> None:
        override_map: dict[str, Component] = {}
        if overrides:
            for comp in overrides:
                override_map[type(comp).component_name()] = comp

        self._data[handle] = {}
        for name, default in self._defaults.items():
            if name in override_map:
                component = deepcopy(override_map[name])
            else:
                component = deepcopy(default)
            self._data[handle][name] = component
            if self._storage:
                self._storage.save_component(handle, name, component.to_dict())

    def remove(self, handle: str) -> None:
        self._data.pop(handle, None)

    # -- Access -------------------------------------------------------------

    def get[T: Component](self, handle: str, component_type: type[T]) -> T:
        name = component_type.component_name()
        return deepcopy(self._data[handle][name])  # type: ignore[return-value]

    def set(self, handle: str, component: Component) -> None:
        name = type(component).component_name()
        self._data[handle][name] = component
        if self._storage:
            self._storage.save_component(handle, name, component.to_dict())

    def has(self, handle: str, component_type: type[Component]) -> bool:
        name = component_type.component_name()
        return handle in self._data and name in self._data[handle]

    def handles(self) -> list[str]:
        return list(self._data.keys())

    # -- Persistence --------------------------------------------------------

    def load_all(self) -> None:
        """Populate in-memory cache from storage."""
        if not self._storage:
            return
        for entity in self._storage.list_entities():
            if entity not in self._data:
                self._data[entity] = {}
            for comp_name in self._storage.list_components(entity):
                comp_type = self._types.get(comp_name)
                if comp_type is None:
                    continue  # skip unknown components (_identity, WORLD state, etc.)
                data = self._storage.load_component(entity, comp_name)
                if data is not None:
                    self._data[entity][comp_name] = comp_type.from_dict(data)
