import json
from pathlib import Path
from time import time


class EventLog:
    def __init__(self, path: Path = Path("data/events.jsonl")):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(path, "a")

    def log(self, entity_id: str, event_type: str, data: dict | None = None):
        event = {
            "t": time(),
            "entity": entity_id,
            "type": event_type,
            "data": data or {},
        }
        self._file.write(json.dumps(event) + "\n")
        self._file.flush()

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        events = []
        for line in self.path.read_text().strip().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return events
