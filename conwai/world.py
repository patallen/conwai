"""Central World container: entities, components, resources, queries."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from typing import TYPE_CHECKING, TypeVar

from conwai.component import Component

if TYPE_CHECKING:
    from conwai.event_bus import EventBus
    from conwai.storage import Storage

log = logging.getLogger("conwai")

T = TypeVar("T", bound=Component)


class World:
    def __init__(self, storage: Storage | None = None, bus: EventBus | None = None):
        self._entities: set[str] = set()
        self._components: dict[str, dict[type, Component]] = {}
        self._defaults: dict[type, Component] = {}
        self._types: dict[str, type[Component]] = {}
        self._resources: dict[type, object] = {}
        self._storage = storage
        self._bus = bus
        self._suppress_events = False

    @property
    def bus(self) -> EventBus | None:
        return self._bus

    # -- Registration --------------------------------------------------------

    def register[T: Component](
        self, comp_type: type[T], default: T | None = None
    ) -> None:
        self._defaults[comp_type] = default if default is not None else comp_type()
        self._types[comp_type.component_name()] = comp_type

    # -- Entities ------------------------------------------------------------

    def spawn(
        self,
        entity_id: str,
        overrides: list[Component] | None = None,
        defaults: bool = True,
    ) -> str:
        if entity_id in self._entities:
            raise ValueError(f"Entity {entity_id!r} already exists")
        self._entities.add(entity_id)
        self._components[entity_id] = {}
        if defaults:
            self._suppress_events = True
            try:
                override_map = {type(c): c for c in (overrides or [])}
                for comp_type, default in self._defaults.items():
                    comp = override_map.get(comp_type, deepcopy(default))
                    self.set(entity_id, comp)
            finally:
                self._suppress_events = False
        if self._bus:
            from conwai.event_types import EntitySpawned
            self._bus.emit(EntitySpawned(entity=entity_id))
        return entity_id

    def destroy(self, entity_id: str) -> None:
        if self._bus and entity_id in self._entities:
            from conwai.event_types import EntityDestroyed
            self._bus.emit(EntityDestroyed(entity=entity_id))
        self._entities.discard(entity_id)
        self._components.pop(entity_id, None)
        if self._storage:
            self._storage.delete_entity(entity_id)

    def entities(self) -> list[str]:
        return list(self._entities)

    # -- Components ----------------------------------------------------------

    def get[T: Component](self, entity: str, comp: type[T]) -> T:
        return self._components[entity][comp]  # type: ignore[return-value]

    def set(self, entity: str, comp: Component) -> None:
        if entity not in self._entities:
            raise KeyError(f"Entity {entity!r} does not exist")
        old = self._components[entity].get(type(comp))
        self._components[entity][type(comp)] = comp
        if self._bus and not self._suppress_events:
            from conwai.event_types import ComponentChanged
            self._bus.emit(ComponentChanged(
                entity=entity,
                comp_type=type(comp),
                old=deepcopy(old) if old is not None else None,
                new=deepcopy(comp),
            ))

    def has(self, entity: str, comp: type[Component]) -> bool:
        return entity in self._components and comp in self._components[entity]

    @contextmanager
    def mutate(self, entity: str, comp_type: type[T]) -> Iterator[T]:
        """Yield the component for in-place mutation; emit ComponentChanged if it changed."""
        comp = self._components[entity][comp_type]
        snapshot = deepcopy(comp)
        try:
            yield comp  # type: ignore[misc]
        except Exception:
            raise
        else:
            if self._bus and comp != snapshot:
                from conwai.event_types import ComponentChanged
                self._bus.emit(ComponentChanged(
                    entity=entity,
                    comp_type=comp_type,
                    old=snapshot,
                    new=deepcopy(comp),
                ))

    # -- Resources -----------------------------------------------------------

    def get_resource[T](self, typ: type[T]) -> T:
        return self._resources[typ]  # type: ignore[return-value]

    def set_resource[T](self, val: T) -> None:
        self._resources[type(val)] = val

    def has_resource(self, typ: type) -> bool:
        return typ in self._resources

    # -- Queries -------------------------------------------------------------

    def query(self, *component_types: type[Component]) -> Iterator[tuple]:
        for entity_id in list(self._entities):
            entity_comps = self._components.get(entity_id, {})
            components = []
            for ct in component_types:
                comp = entity_comps.get(ct)
                if comp is None:
                    break
                components.append(comp)
            else:
                yield (entity_id, *components)

    # -- Persistence ---------------------------------------------------------

    def flush(self) -> None:
        """Persist all in-memory components to storage."""
        if not self._storage:
            return
        for entity_id in self._entities:
            for comp in self._components.get(entity_id, {}).values():
                self._storage.save_component(
                    entity_id, type(comp).component_name(), comp.to_dict()
                )

    def save_metadata(self, key: str, data: dict) -> None:
        """Persist non-entity data (tick counter, world state) to storage."""
        if self._storage:
            self._storage.save_component("_meta", key, data)

    def load_metadata(self, key: str) -> dict | None:
        """Load non-entity data from storage."""
        if self._storage:
            return self._storage.load_component("_meta", key)
        return None

    def save_raw(self, entity_id: str, key: str, data: dict) -> None:
        """Save arbitrary data for an entity (bypasses Component system)."""
        if self._storage:
            self._storage.save_component(entity_id, key, data)

    def load_raw(self, entity_id: str, key: str) -> dict | None:
        """Load arbitrary data for an entity."""
        if self._storage:
            return self._storage.load_component(entity_id, key)
        return None

    def load_all(self) -> None:
        if not self._storage:
            return
        for entity_id in self._storage.list_entities():
            # Only load entities that have at least one registered component
            comp_names = self._storage.list_components(entity_id)
            if not any(name in self._types for name in comp_names):
                continue
            self._entities.add(entity_id)
            if entity_id not in self._components:
                self._components[entity_id] = {}
            for comp_name in comp_names:
                comp_type = self._types.get(comp_name)
                if comp_type is None:
                    continue
                data = self._storage.load_component(entity_id, comp_name)
                if data is not None:
                    self._components[entity_id][comp_type] = comp_type.from_dict(data)
