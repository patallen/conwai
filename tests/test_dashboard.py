import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from conwai.dashboard import app

client = TestClient(app)


def test_status_returns_tick_alive_total(tmp_path):
    tick_file = tmp_path / "tick"
    tick_file.write_text("42")
    events_file = tmp_path / "events.jsonl"
    events_file.write_text('{"t":1,"entity":"a","type":"x","data":{}}\n' * 3)
    agents_dir = tmp_path / "agents"
    (agents_dir / "agent1").mkdir(parents=True)
    (agents_dir / "agent1" / "alive").write_text("true")
    (agents_dir / "agent2").mkdir(parents=True)
    (agents_dir / "agent2" / "alive").write_text("false")

    with (
        patch("conwai.dashboard.EVENTS_PATH", events_file),
        patch("conwai.dashboard.AGENTS_DIR", agents_dir),
        patch("conwai.dashboard.TICK_PATH", tick_file),
    ):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tick"] == 42
        assert data["alive"] == 1
        assert data["total_events"] == 3


def test_handler_structured_post_board(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "post_board", "content": "hello world"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert handler_file.read_text().strip() == "hello world"


def test_handler_structured_send_dm(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "send_dm", "to": "abc123", "content": "hey"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert handler_file.read_text().strip() == "@abc123 hey"


def test_handler_structured_set_energy(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "set_energy", "handle": "abc123", "value": 500})
        assert resp.status_code == 200
        assert handler_file.read_text().strip() == "!set_energy abc123 500"


def test_handler_structured_drain_energy(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "drain_energy", "handle": "abc123", "amount": 100})
        assert resp.status_code == 200
        assert handler_file.read_text().strip() == "!drain abc123 100"


def test_handler_structured_drop_secret(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "drop_secret", "handle": "abc123", "content": "a secret"})
        assert resp.status_code == 200
        assert handler_file.read_text().strip() == "!secret abc123 a secret"


def test_handler_structured_unknown_action(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "unknown_thing"})
        assert resp.status_code == 400
        assert resp.json()["ok"] is False


def test_handler_legacy_message_still_works(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"message": "hello board"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert handler_file.read_text().strip() == "hello board"
