"""Configuration for the commons scenario."""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("conwai")

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"
_config: CommonsConfig | None = None

@dataclass
class CommonsConfig:
    pond_capacity: float = 1000.0
    pond_starting_population: float = 1000.0
    pond_growth_rate: float = 0.05
    pond_collapse_threshold: float = 100.0
    fish_min: int = 1
    fish_max: int = 20
    fish_default: int = 5
    fish_interval: int = 3
    agent_count: int = 8
    personality: str = "practical, observant"
    board_max_posts: int = 30
    board_max_post_length: int = 200
    dm_limit_per_tick: int = 2
    context_window: int = 16000
    memory_max: int = 1000
    max_ticks: int = 1000
    seed: int | None = None
    activation_cost: int = 0
    retrigger_cost: int = 1

    @classmethod
    def from_file(cls, path: Path | None = None) -> CommonsConfig:
        path = path or _DEFAULT_CONFIG_PATH
        if not path.exists():
            return cls()
        with open(path) as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def get_config() -> CommonsConfig:
    global _config
    if _config is None:
        _config = CommonsConfig.from_file()
    return _config


def reload():
    global _config
    _config = CommonsConfig.from_file()
