import json
from pathlib import Path

_CONFIG_PATH = Path("config.json")


def load() -> dict:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text())
    return {}


CFG = load()

# Energy
ENERGY_MAX = CFG.get("energy_max", 1000)
ENERGY_COST_PER_WORD = CFG.get(
    "energy_cost_per_word",
    {
        "post_to_board": 2,
        "send_message": 1,
        "remember": 1,
    },
)
ENERGY_COST_FLAT = CFG.get(
    "energy_cost_flat",
    {
        "recall": 0,
        "update_soul": 5,
    },
)
ENERGY_GAIN = CFG.get(
    "energy_gain",
    {
        "referenced": 10,
        "dm_received": 5,
    },
)

# Board
BOARD_MAX_POSTS = CFG.get("board_max_posts", 30)
BOARD_MAX_POST_LENGTH = CFG.get("board_max_post_length", 200)

# Heartbeat
HEARTBEAT_INTERVAL = CFG.get("heartbeat_interval", 5.0)

# Personality
TRAITS = [
    "skeptical",
    "detached",
    "calculating",
    "deliberate",
    "secretive",
    "dry",
    "competitive",
    "blunt",
    "laid-back",
    "cautious",
    "stoic",
    "patient",
]

# Food / Hunger
HUNGER_MAX = CFG.get("hunger_max", 100)
HUNGER_DECAY_PER_TICK = CFG.get("hunger_decay_per_tick", 3)
HUNGER_AUTO_EAT_THRESHOLD = CFG.get("hunger_auto_eat_threshold", 80)
HUNGER_EAT_RESTORE = CFG.get("hunger_eat_restore", 15)
HUNGER_STARVE_COIN_PENALTY = CFG.get("hunger_starve_coin_penalty", 10)

# Roles and foraging
ROLES = ["flour_forager", "water_forager", "baker"]
FORAGE_SKILL_BY_ROLE = CFG.get("forage_skill_by_role", {
    "flour_forager": {"flour": 4, "water": 1},
    "water_forager": {"flour": 1, "water": 4},
    "baker": {"flour": 1, "water": 1},
})
STARTING_BREAD = CFG.get("starting_bread", 5)
BAKE_COST = CFG.get("bake_cost", {"flour": 1, "water": 1})  # inputs per bake
BAKE_YIELD = CFG.get("bake_yield", 2)  # bread produced per bake

# State window sizes (shown in system prompt)
STATE_BOARD_LENGTH = CFG.get("state_board_length", 10)
STATE_INTERACTIONS_LENGTH = CFG.get("state_interactions_length", 10)
STATE_LEDGER_LENGTH = CFG.get("state_ledger_length", 10)

# Context window (chars)
CONTEXT_WINDOW = CFG.get("context_window", 16000)

# Scratchpad
MEMORY_MAX = CFG.get("memory_max", CFG.get("scratchpad_max", 1000))
