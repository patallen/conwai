import json
import random as _random
from pathlib import Path

_CONFIG_PATH = Path("config.json")


def load() -> dict:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text())
    return {}


def _get(cfg: dict, *keys, default=None):
    """Read from nested config."""
    val = cfg
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
    return val if val is not None else default


def reload():
    """Re-read config.json and update all module globals."""
    cfg = load()
    g = globals()
    g["CFG"] = cfg

    # Starting resources
    g["STARTING_COINS"] = _get(cfg, "starting", "coins", default=500)
    g["STARTING_FLOUR"] = _get(cfg, "starting", "flour", default=0)
    g["STARTING_WATER"] = _get(cfg, "starting", "water", default=0)
    g["STARTING_BREAD"] = _get(cfg, "starting", "bread", default=5)
    g["STARTING_HUNGER"] = _get(cfg, "starting", "hunger", default=100)
    g["STARTING_THIRST"] = _get(cfg, "starting", "thirst", default=100)

    # Economy
    g["ENERGY_MAX"] = _get(cfg, "economy", "max_coins", default=1000)
    g["ENERGY_COST_FLAT"] = _get(cfg, "economy", "cost_flat", default={"update_soul": 5})
    g["ENERGY_GAIN"] = _get(cfg, "economy", "gain", default={"referenced": 10, "dm_received": 5})

    # Board
    g["BOARD_MAX_POSTS"] = _get(cfg, "board", "max_posts", default=30)
    g["BOARD_MAX_POST_LENGTH"] = _get(cfg, "board", "max_post_length", default=200)

    # Hunger
    g["HUNGER_MAX"] = _get(cfg, "hunger", "max", default=100)
    g["HUNGER_DECAY_PER_TICK"] = _get(cfg, "hunger", "decay_per_tick", default=3)
    g["HUNGER_AUTO_EAT_THRESHOLD"] = _get(cfg, "hunger", "auto_eat_threshold", default=80)
    g["HUNGER_EAT_RESTORE"] = _get(cfg, "hunger", "eat_restore", default=15)
    g["HUNGER_EAT_RAW_RESTORE"] = _get(cfg, "hunger", "eat_raw_restore", default=5)
    g["HUNGER_STARVE_COIN_PENALTY"] = _get(cfg, "hunger", "starve_coin_penalty", default=10)

    # Thirst
    g["THIRST_DECAY_PER_TICK"] = _get(cfg, "thirst", "decay_per_tick", default=3)
    g["THIRST_AUTO_DRINK_THRESHOLD"] = _get(cfg, "thirst", "auto_drink_threshold", default=80)
    g["THIRST_DRINK_RESTORE"] = _get(cfg, "thirst", "drink_restore", default=15)
    g["THIRST_DEHYDRATION_COIN_PENALTY"] = _get(cfg, "thirst", "dehydration_coin_penalty", default=10)
    g["PASSIVE_WATER_PER_TICK"] = _get(cfg, "thirst", "passive_water_per_tick", default=0)

    # Foraging
    g["ROLES"] = _get(cfg, "foraging", "roles", default=["flour_forager", "water_forager", "baker"])
    g["FORAGE_SKILL_BY_ROLE"] = _get(cfg, "foraging", "skill_by_role", default={
        "flour_forager": {"flour": 4, "water": 1},
        "water_forager": {"flour": 1, "water": 4},
        "baker": {"flour": 1, "water": 1},
    })

    # Baking
    g["BAKE_COST"] = _get(cfg, "baking", "cost", default={"flour": 1, "water": 1})
    g["BAKE_YIELD"] = _get(cfg, "baking", "yield", default=2)

    # Spoilage
    g["BREAD_SPOIL_INTERVAL"] = _get(cfg, "spoilage", "interval", default=6)
    g["BREAD_SPOIL_AMOUNT"] = _get(cfg, "spoilage", "amount", default=1)

    # Brain
    g["CONTEXT_WINDOW"] = _get(cfg, "brain", "context_window", default=16000)
    g["MEMORY_MAX"] = _get(cfg, "brain", "memory_max", default=1000)

    # Perception
    g["STATE_BOARD_LENGTH"] = _get(cfg, "perception", "board_length", default=10)
    g["STATE_INTERACTIONS_LENGTH"] = _get(cfg, "perception", "interactions_length", default=10)
    g["STATE_LEDGER_LENGTH"] = _get(cfg, "perception", "ledger_length", default=10)


CFG = load()

# Bootstrap all globals from initial config
reload()

# Personality traits
TRAITS = [
    "skeptical", "detached", "calculating", "deliberate", "secretive",
    "dry", "competitive", "blunt", "laid-back", "cautious", "stoic", "patient",
]

_available_traits: set[str] = set(TRAITS)


def assign_traits(n: int = 2) -> list[str]:
    if len(_available_traits) < n:
        _available_traits.update(TRAITS)
    chosen = _random.sample(sorted(_available_traits), n)
    _available_traits.difference_update(chosen)
    return chosen
