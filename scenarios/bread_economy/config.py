import random as _random

from conwai.config import get, load

_CONFIG_PATH_DEFAULT = "config.json"


def reload():
    """Re-read config.json and update all module globals."""
    cfg = load()
    g = globals()
    g["CFG"] = cfg

    # Starting resources
    g["STARTING_COINS"] = get(cfg, "starting", "coins", default=500)
    g["STARTING_FLOUR"] = get(cfg, "starting", "flour", default=0)
    g["STARTING_WATER"] = get(cfg, "starting", "water", default=0)
    g["STARTING_BREAD"] = get(cfg, "starting", "bread", default=5)
    g["STARTING_HUNGER"] = get(cfg, "starting", "hunger", default=100)
    g["STARTING_THIRST"] = get(cfg, "starting", "thirst", default=100)

    # Economy
    g["ENERGY_MAX"] = get(cfg, "economy", "max_coins", default=1000)
    g["ENERGY_COST_FLAT"] = get(cfg, "economy", "cost_flat", default={"update_soul": 5})
    g["ENERGY_GAIN"] = get(cfg, "economy", "gain", default={"referenced": 10, "dm_received": 5})

    # Board
    g["BOARD_MAX_POSTS"] = get(cfg, "board", "max_posts", default=30)
    g["BOARD_MAX_POST_LENGTH"] = get(cfg, "board", "max_post_length", default=200)

    # Hunger
    g["HUNGER_MAX"] = get(cfg, "hunger", "max", default=100)
    g["HUNGER_DECAY_PER_TICK"] = get(cfg, "hunger", "decay_per_tick", default=3)
    g["HUNGER_AUTO_EAT_THRESHOLD"] = get(cfg, "hunger", "auto_eat_threshold", default=80)
    g["HUNGER_EAT_RESTORE"] = get(cfg, "hunger", "eat_restore", default=15)
    g["HUNGER_EAT_RAW_RESTORE"] = get(cfg, "hunger", "eat_raw_restore", default=5)
    g["HUNGER_STARVE_COIN_PENALTY"] = get(cfg, "hunger", "starve_coin_penalty", default=10)

    # Thirst
    g["THIRST_DECAY_PER_TICK"] = get(cfg, "thirst", "decay_per_tick", default=3)
    g["THIRST_AUTO_DRINK_THRESHOLD"] = get(cfg, "thirst", "auto_drink_threshold", default=80)
    g["THIRST_DRINK_RESTORE"] = get(cfg, "thirst", "drink_restore", default=15)
    g["THIRST_DEHYDRATION_COIN_PENALTY"] = get(cfg, "thirst", "dehydration_coin_penalty", default=10)
    g["PASSIVE_WATER_PER_TICK"] = get(cfg, "thirst", "passive_water_per_tick", default=0)

    # Foraging
    g["ROLES"] = get(cfg, "foraging", "roles", default=["flour_forager", "water_forager", "baker"])
    g["FORAGE_SKILL_BY_ROLE"] = get(cfg, "foraging", "skill_by_role", default={
        "flour_forager": {"flour": 4, "water": 1},
        "water_forager": {"flour": 1, "water": 4},
        "baker": {"flour": 1, "water": 1},
    })

    # Inventory
    g["INVENTORY_CAP"] = get(cfg, "inventory", "cap", default=100)

    # Baking
    g["BAKE_COST"] = get(cfg, "baking", "cost", default={"flour": 3, "water": 3})
    g["BAKE_YIELD"] = get(cfg, "baking", "yield", default=2)
    g["BAKE_BAKER_YIELD"] = get(cfg, "baking", "baker_yield", default=3)

    # Spoilage
    g["BREAD_SPOIL_INTERVAL"] = get(cfg, "spoilage", "interval", default=6)
    g["BREAD_SPOIL_AMOUNT"] = get(cfg, "spoilage", "amount", default=1)

    # Brain
    g["CONTEXT_WINDOW"] = get(cfg, "brain", "context_window", default=16000)
    g["MEMORY_MAX"] = get(cfg, "brain", "memory_max", default=1000)

    # Perception
    g["STATE_BOARD_LENGTH"] = get(cfg, "perception", "board_length", default=10)
    g["STATE_INTERACTIONS_LENGTH"] = get(cfg, "perception", "interactions_length", default=10)
    g["STATE_LEDGER_LENGTH"] = get(cfg, "perception", "ledger_length", default=10)

    # Role descriptions — agents discover their strengths through experience
    bc = g["BAKE_COST"]
    by = g["BAKE_YIELD"]
    generic_desc = "You automatically forage and bake each tick. Your foraging yields vary — you produce more of some resources than others. Trade to get what you're short on."
    g["ROLE_DESCRIPTIONS"] = get(cfg, "roles", "descriptions", default={
        "flour_forager": generic_desc,
        "water_forager": generic_desc,
    })


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


def register_components(store) -> None:
    """Register all bread-economy components on a ComponentStore."""
    store.register_component("agent_info", {"role": "", "personality": ""})
