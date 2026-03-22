from conwai.bulletin_board import BulletinBoard
from conwai.messages import MessageBus
from conwai.storage import SQLiteStorage


def test_sqlite_save_load(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    storage.save_component("A1", "economy", {"coins": 500})
    result = storage.load_component("A1", "economy")
    assert result == {"coins": 500}


def test_sqlite_list_entities(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    storage.save_component("A1", "economy", {"coins": 500})
    storage.save_component("A2", "economy", {"coins": 300})
    assert sorted(storage.list_entities()) == ["A1", "A2"]


def test_sqlite_overwrite(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    storage.save_component("A1", "economy", {"coins": 500})
    storage.save_component("A1", "economy", {"coins": 300})
    assert storage.load_component("A1", "economy") == {"coins": 300}


def test_sqlite_missing_returns_none(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    assert storage.load_component("A1", "economy") is None


def test_sqlite_list_components(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    storage.save_component("A1", "economy", {"coins": 500})
    storage.save_component("A1", "inventory", {"flour": 3})
    assert sorted(storage.list_components("A1")) == ["economy", "inventory"]


def test_board_persistence(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    board = BulletinBoard(storage=storage)
    board.post("A1", "hello world")
    # Create a new board from the same storage
    board2 = BulletinBoard(storage=storage)
    assert len(board2._posts) == 1
    assert board2._posts[0].content == "hello world"


def test_bus_persistence(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    bus = MessageBus(storage=storage)
    bus.register("A1")
    bus.register("A2")
    bus.send("A1", "A2", "hello")
    # Create a new bus from the same storage
    bus2 = MessageBus(storage=storage)
    msgs = bus2.receive("A2")
    assert len(msgs) == 1
    assert msgs[0].content == "hello"
