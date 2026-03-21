from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.storage import Storage


class ComponentStore:
    def __init__(self, storage: Storage | None = None):
        self._defaults: dict[str, dict] = {}
        self._data: dict[str, dict[str, dict]] = {}  # handle -> component -> data
        self._storage = storage

    def register_component(self, name: str, defaults: dict) -> None:
        self._defaults[name] = defaults

    def init_agent(self, handle: str, overrides: dict[str, dict] | None = None) -> None:
        self._data[handle] = {}
        for name, defaults in self._defaults.items():
            if overrides and name in overrides:
                data = deepcopy(overrides[name])
            else:
                data = deepcopy(defaults)
            self._data[handle][name] = data
            if self._storage:
                self._storage.save_component(handle, name, data)

    def get(self, handle: str, component: str) -> dict:
        return deepcopy(self._data[handle][component])

    def set(self, handle: str, component: str, data: dict) -> None:
        self._data[handle][component] = data
        if self._storage:
            self._storage.save_component(handle, component, data)

    def has(self, handle: str, component: str) -> bool:
        return handle in self._data and component in self._data[handle]

    def remove(self, handle: str) -> None:
        self._data.pop(handle, None)
        # Note: we don't delete from storage -- dead agents' data is kept for history

    def handles(self) -> list[str]:
        return list(self._data.keys())

    def load_all(self) -> None:
        """Populate in-memory cache from storage."""
        if not self._storage:
            return
        for entity in self._storage.list_entities():
            self._data[entity] = {}
            for component in self._storage.list_components(entity):
                data = self._storage.load_component(entity, component)
                if data is not None:
                    self._data[entity][component] = data
