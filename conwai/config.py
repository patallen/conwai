import json
from pathlib import Path

_CONFIG_PATH = Path("config.json")


def load(path: Path | None = None) -> dict:
    p = path or _CONFIG_PATH
    if p.exists():
        return json.loads(p.read_text())
    return {}


def get(cfg: dict, *keys, default=None):
    """Read from nested config."""
    val: object = cfg
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
    return val if val is not None else default
