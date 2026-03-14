import json
from pathlib import Path
from time import time


class EventLog:
    def __init__(self, path: Path = Path("events.jsonl")):
        self.path = path
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
