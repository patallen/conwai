from dataclasses import dataclass

from conwai.component import Component
from conwai.storage import SQLiteStorage
from conwai.world import World


@dataclass
class Health(Component):
    hp: int = 100


@dataclass
class Position(Component):
    x: int = 0
    y: int = 0


@dataclass
class TickNumber:
    value: int = 0


# -- Task 1: Component storage ------------------------------------------------


def test_set_and_get_component():
    world = World()
    world.spawn("e1")
    world.set("e1", Health(hp=50))
    h = world.get("e1", Health)
    assert h.hp == 50


def test_has_component():
    world = World()
    world.spawn("e1")
    assert not world.has("e1", Health)
    world.set("e1", Health())
    assert world.has("e1", Health)


def test_get_returns_reference_not_copy():
    world = World()
    world.spawn("e1")
    world.set("e1", Health(hp=100))
    h = world.get("e1", Health)
    h.hp = 50
    assert world.get("e1", Health).hp == 50


# -- Task 2: Entity lifecycle -------------------------------------------------


def test_spawn_and_entities():
    world = World()
    world.spawn("e1")
    world.spawn("e2")
    assert set(world.entities()) == {"e1", "e2"}


def test_destroy_removes_entity():
    world = World()
    world.spawn("e1")
    world.destroy("e1")
    assert "e1" not in world.entities()


def test_register_defaults():
    world = World()
    world.register(Health, Health(hp=50))
    world.spawn("e1")
    assert world.get("e1", Health).hp == 50


def test_spawn_with_overrides():
    world = World()
    world.register(Health, Health(hp=50))
    world.register(Position, Position(x=0, y=0))
    world.spawn("e1", overrides=[Health(hp=99)])
    assert world.get("e1", Health).hp == 99
    assert world.get("e1", Position).x == 0


def test_spawn_without_defaults():
    world = World()
    world.register(Health, Health(hp=50))
    world.spawn("e1", defaults=False)
    assert not world.has("e1", Health)


# -- Task 3: Resources and queries --------------------------------------------


def test_set_and_get_resource():
    world = World()
    world.set_resource(TickNumber(42))
    assert world.get_resource(TickNumber).value == 42


def test_has_resource():
    world = World()
    assert not world.has_resource(TickNumber)
    world.set_resource(TickNumber(0))
    assert world.has_resource(TickNumber)


def test_resource_returns_reference():
    world = World()
    world.set_resource(TickNumber(0))
    t = world.get_resource(TickNumber)
    t.value = 5
    assert world.get_resource(TickNumber).value == 5


def test_query_single_component():
    world = World()
    world.spawn("e1", defaults=False)
    world.spawn("e2", defaults=False)
    world.set("e1", Health(hp=10))
    world.set("e2", Health(hp=20))
    results = list(world.query(Health))
    assert len(results) == 2
    entities = {r[0] for r in results}
    assert entities == {"e1", "e2"}


def test_query_multiple_components():
    world = World()
    world.spawn("e1", defaults=False)
    world.spawn("e2", defaults=False)
    world.set("e1", Health(hp=10))
    world.set("e1", Position(x=1, y=2))
    world.set("e2", Health(hp=20))  # no Position
    results = list(world.query(Health, Position))
    assert len(results) == 1
    entity, h, p = results[0]
    assert entity == "e1"
    assert h.hp == 10
    assert p.x == 1


def test_query_returns_references():
    world = World()
    world.spawn("e1", defaults=False)
    world.set("e1", Health(hp=100))
    for entity, h in world.query(Health):
        h.hp = 50
    assert world.get("e1", Health).hp == 50


# -- Task 4: Persistence ------------------------------------------------------


def test_set_persists_to_storage(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    world = World(storage=storage)
    world.spawn("e1", defaults=False)
    world.set("e1", Health(hp=42))
    data = storage.load_component("e1", "health")
    assert data == {"hp": 42}


def test_load_all_restores_state(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    world1 = World(storage=storage)
    world1.register(Health)
    world1.spawn("e1", defaults=False)
    world1.set("e1", Health(hp=42))

    world2 = World(storage=storage)
    world2.register(Health)
    world2.load_all()
    assert "e1" in world2.entities()
    assert world2.get("e1", Health).hp == 42


def test_destroy_persists(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    world = World(storage=storage)
    world.register(Health)
    world.spawn("e1")
    world.destroy("e1")
    world2 = World(storage=storage)
    world2.register(Health)
    world2.load_all()
    assert "e1" not in world2.entities()
