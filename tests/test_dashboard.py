from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from conwai.storage import SQLiteStorage
from scenarios.bread_economy.dashboard import app

client = TestClient(app)


def test_status_returns_tick_alive_total(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    storage.save_component("WORLD", "tick", {"value": 42})
    storage.save_component("agent1", "agent_info", {"role": "forager", "personality": "bold"})
    storage.save_component("agent2", "agent_info", {"role": "baker", "personality": "shy"})

    mock_events = MagicMock()
    mock_events.count.return_value = 3

    with (
        patch("scenarios.bread_economy.dashboard._events", mock_events),
        patch("scenarios.bread_economy.dashboard._storage", storage),
    ):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tick"] == 42
        assert data["alive"] == 2
        assert data["total_events"] == 3


def test_handler_structured_post_board(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    with patch("scenarios.bread_economy.dashboard._storage", storage):
        resp = client.post("/api/handler", json={"action": "post_board", "content": "hello world"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        cmds = storage.pop_commands()
        assert len(cmds) == 1
        assert cmds[0] == {"action": "post_board", "content": "hello world"}


def test_handler_structured_send_dm(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    with patch("scenarios.bread_economy.dashboard._storage", storage):
        resp = client.post("/api/handler", json={"action": "send_dm", "to": "abc123", "content": "hey"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        cmds = storage.pop_commands()
        assert cmds[0]["action"] == "send_dm"
        assert cmds[0]["to"] == "abc123"


def test_handler_structured_set_energy(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    with patch("scenarios.bread_economy.dashboard._storage", storage):
        resp = client.post("/api/handler", json={"action": "set_energy", "handle": "abc123", "value": 500})
        assert resp.status_code == 200
        cmds = storage.pop_commands()
        assert cmds[0]["action"] == "set_energy"
        assert cmds[0]["handle"] == "abc123"
        assert cmds[0]["value"] == 500


def test_handler_structured_drain_energy(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    with patch("scenarios.bread_economy.dashboard._storage", storage):
        resp = client.post("/api/handler", json={"action": "drain_energy", "handle": "abc123", "amount": 100})
        assert resp.status_code == 200
        cmds = storage.pop_commands()
        assert cmds[0]["action"] == "drain_energy"
        assert cmds[0]["amount"] == 100


def test_handler_structured_drop_secret(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    with patch("scenarios.bread_economy.dashboard._storage", storage):
        resp = client.post("/api/handler", json={"action": "drop_secret", "handle": "abc123", "content": "a secret"})
        assert resp.status_code == 200
        cmds = storage.pop_commands()
        assert cmds[0]["action"] == "drop_secret"
        assert cmds[0]["content"] == "a secret"


def test_handler_structured_unknown_action(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    with patch("scenarios.bread_economy.dashboard._storage", storage):
        resp = client.post("/api/handler", json={"action": "unknown_thing"})
        assert resp.status_code == 400
        assert resp.json()["ok"] is False


def test_handler_legacy_message_still_works(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    with patch("scenarios.bread_economy.dashboard._storage", storage):
        resp = client.post("/api/handler", json={"message": "hello board"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        cmds = storage.pop_commands()
        assert cmds[0] == {"action": "post_board", "content": "hello board"}
