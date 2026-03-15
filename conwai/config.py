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
HEARTBEAT_INTERVAL = CFG.get("heartbeat_interval", 3.0)

# Personality
TRAITS = [
    "contrarian",
    "curious",
    "impatient",
    "cautious",
    "blunt",
    "playful",
    "skeptical",
    "restless",
    "deliberate",
    "provocative",
    "warm",
    "detached",
    "intense",
    "laid-back",
    "obsessive",
    "irreverent",
    "earnest",
    "dry",
    "anxious",
    "stubborn",
    "competitive",
    "secretive",
    "generous",
    "paranoid",
    "methodical",
    "impulsive",
    "stoic",
    "dramatic",
    "calculating",
    "sentimental",
    "defiant",
    "patient",
    "cynical",
    "idealistic",
    "territorial",
    "nomadic",
    "vengeful",
    "forgiving",
    "ambitious",
    "apathetic",
]

# Sleep
SLEEP_REGEN_PER_TICK = CFG.get("sleep_regen_per_tick", 10)

# Short-term memory
CONTEXT_WINDOW = CFG.get("context_window", 10)

# Scratchpad
SCRATCHPAD_MAX = CFG.get("scratchpad_max", 1000)
