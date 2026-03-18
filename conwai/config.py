import json
from pathlib import Path

_CONFIG_PATH = Path("config.json")


def load() -> dict:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text())
    return {}


def reload():
    """Re-read config.json and update all module globals."""
    cfg = load()
    g = globals()
    g["CFG"] = cfg
    g["ENERGY_MAX"] = cfg.get("energy_max", 1000)
    g["ENERGY_COST_PER_WORD"] = cfg.get("energy_cost_per_word", {
        "post_to_board": 2, "send_message": 1, "remember": 1,
    })
    g["ENERGY_COST_FLAT"] = cfg.get("energy_cost_flat", {"recall": 0, "update_soul": 5})
    g["ENERGY_GAIN"] = cfg.get("energy_gain", {"referenced": 10, "dm_received": 5})
    g["BOARD_MAX_POSTS"] = cfg.get("board_max_posts", 30)
    g["BOARD_MAX_POST_LENGTH"] = cfg.get("board_max_post_length", 200)
    g["HUNGER_MAX"] = cfg.get("hunger_max", 100)
    g["HUNGER_DECAY_PER_TICK"] = cfg.get("hunger_decay_per_tick", 3)
    g["HUNGER_AUTO_EAT_THRESHOLD"] = cfg.get("hunger_auto_eat_threshold", 80)
    g["HUNGER_EAT_RESTORE"] = cfg.get("hunger_eat_restore", 15)
    g["HUNGER_EAT_RAW_RESTORE"] = cfg.get("hunger_eat_raw_restore", 5)
    g["HUNGER_STARVE_COIN_PENALTY"] = cfg.get("hunger_starve_coin_penalty", 10)
    g["THIRST_DECAY_PER_TICK"] = cfg.get("thirst_decay_per_tick", 3)
    g["THIRST_AUTO_DRINK_THRESHOLD"] = cfg.get("thirst_auto_drink_threshold", 80)
    g["THIRST_DRINK_RESTORE"] = cfg.get("thirst_drink_restore", 15)
    g["THIRST_DEHYDRATION_COIN_PENALTY"] = cfg.get("thirst_dehydration_coin_penalty", 10)
    g["PASSIVE_WATER_PER_TICK"] = cfg.get("passive_water_per_tick", 0)
    g["FORAGE_SKILL_BY_ROLE"] = cfg.get("forage_skill_by_role", {
        "flour_forager": {"flour": 4, "water": 1},
        "water_forager": {"flour": 1, "water": 4},
        "baker": {"flour": 1, "water": 1},
    })
    g["STARTING_BREAD"] = cfg.get("starting_bread", 5)
    g["BAKE_COST"] = cfg.get("bake_cost", {"flour": 1, "water": 1})
    g["BAKE_YIELD"] = cfg.get("bake_yield", 2)
    g["BREAD_SPOIL_INTERVAL"] = cfg.get("bread_spoil_interval", 6)
    g["BREAD_SPOIL_AMOUNT"] = cfg.get("bread_spoil_amount", 1)
    g["STATE_BOARD_LENGTH"] = cfg.get("state_board_length", 10)
    g["STATE_INTERACTIONS_LENGTH"] = cfg.get("state_interactions_length", 10)
    g["STATE_LEDGER_LENGTH"] = cfg.get("state_ledger_length", 10)
    g["CONTEXT_WINDOW"] = cfg.get("context_window", 16000)
    g["MEMORY_MAX"] = cfg.get("memory_max", cfg.get("scratchpad_max", 1000))


CFG = load()

# Energy
ENERGY_MAX = CFG.get("energy_max", 1000)
ENERGY_COST_PER_WORD = CFG.get("energy_cost_per_word", {
    "post_to_board": 2, "send_message": 1, "remember": 1,
})
ENERGY_COST_FLAT = CFG.get("energy_cost_flat", {"recall": 0, "update_soul": 5})
ENERGY_GAIN = CFG.get("energy_gain", {"referenced": 10, "dm_received": 5})

# Board
BOARD_MAX_POSTS = CFG.get("board_max_posts", 30)
BOARD_MAX_POST_LENGTH = CFG.get("board_max_post_length", 200)

# Personality
TRAITS = [
    "skeptical", "detached", "calculating", "deliberate", "secretive",
    "dry", "competitive", "blunt", "laid-back", "cautious", "stoic", "patient",
]

# Food / Hunger
HUNGER_MAX = CFG.get("hunger_max", 100)
HUNGER_DECAY_PER_TICK = CFG.get("hunger_decay_per_tick", 3)
HUNGER_AUTO_EAT_THRESHOLD = CFG.get("hunger_auto_eat_threshold", 80)
HUNGER_EAT_RESTORE = CFG.get("hunger_eat_restore", 15)
HUNGER_EAT_RAW_RESTORE = CFG.get("hunger_eat_raw_restore", 5)
HUNGER_STARVE_COIN_PENALTY = CFG.get("hunger_starve_coin_penalty", 10)
THIRST_DECAY_PER_TICK = CFG.get("thirst_decay_per_tick", 3)
THIRST_AUTO_DRINK_THRESHOLD = CFG.get("thirst_auto_drink_threshold", 80)
THIRST_DRINK_RESTORE = CFG.get("thirst_drink_restore", 15)
THIRST_DEHYDRATION_COIN_PENALTY = CFG.get("thirst_dehydration_coin_penalty", 10)
PASSIVE_WATER_PER_TICK = CFG.get("passive_water_per_tick", 0)

# Roles and foraging
ROLES = ["flour_forager", "water_forager", "baker"]
FORAGE_SKILL_BY_ROLE = CFG.get("forage_skill_by_role", {
    "flour_forager": {"flour": 4, "water": 1},
    "water_forager": {"flour": 1, "water": 4},
    "baker": {"flour": 1, "water": 1},
})
STARTING_BREAD = CFG.get("starting_bread", 5)
BAKE_COST = CFG.get("bake_cost", {"flour": 1, "water": 1})
BAKE_YIELD = CFG.get("bake_yield", 2)
BREAD_SPOIL_INTERVAL = CFG.get("bread_spoil_interval", 6)
BREAD_SPOIL_AMOUNT = CFG.get("bread_spoil_amount", 1)

# State window sizes (shown in system prompt)
STATE_BOARD_LENGTH = CFG.get("state_board_length", 10)
STATE_INTERACTIONS_LENGTH = CFG.get("state_interactions_length", 10)
STATE_LEDGER_LENGTH = CFG.get("state_ledger_length", 10)

# Context window (chars)
CONTEXT_WINDOW = CFG.get("context_window", 16000)

# Scratchpad
MEMORY_MAX = CFG.get("memory_max", CFG.get("scratchpad_max", 1000))
