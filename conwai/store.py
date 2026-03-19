from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


class ComponentStore:
    def __init__(self):
        self._defaults: dict[str, dict] = {}
        self._data: dict[str, dict[str, dict]] = {}  # handle -> component -> data

    def register_component(self, name: str, defaults: dict) -> None:
        self._defaults[name] = defaults

    def init_agent(self, handle: str, overrides: dict[str, dict] | None = None) -> None:
        self._data[handle] = {}
        for name, defaults in self._defaults.items():
            if overrides and name in overrides:
                self._data[handle][name] = deepcopy(overrides[name])
            else:
                self._data[handle][name] = deepcopy(defaults)

    def get(self, handle: str, component: str) -> dict:
        return self._data[handle][component]

    def set(self, handle: str, component: str, data: dict) -> None:
        self._data[handle][component] = data

    def has(self, handle: str, component: str) -> bool:
        return handle in self._data and component in self._data[handle]

    def remove(self, handle: str) -> None:
        self._data.pop(handle, None)

    def handles(self) -> list[str]:
        return list(self._data.keys())

    def save(self, handle: str, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if handle not in self._data:
            return
        for component, data in self._data[handle].items():
            (path / f"{component}.json").write_text(json.dumps(data))

    def load(self, handle: str, path: Path) -> None:
        self._data[handle] = {}
        for name in self._defaults:
            fpath = path / f"{name}.json"
            if fpath.exists():
                self._data[handle][name] = json.loads(fpath.read_text())
            else:
                self._data[handle][name] = deepcopy(self._defaults[name])
