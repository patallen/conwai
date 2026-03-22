from __future__ import annotations

import random as _random
from dataclasses import dataclass, field

from conwai.config import get, load


@dataclass
class ScenarioConfig:
    """Typed configuration for the bread economy scenario."""

    # Starting resources
    starting_coins: int = 500
    starting_flour: int = 0
    starting_water: int = 0
    starting_bread: int = 5
    starting_hunger: int = 100
    starting_thirst: int = 100

    # Economy
    energy_max: int = 1000
    energy_cost_flat: dict = field(default_factory=lambda: {"update_soul": 5})
    energy_gain: dict = field(
        default_factory=lambda: {"referenced": 10, "dm_received": 5}
    )

    # Board
    board_max_posts: int = 30
    board_max_post_length: int = 200

    # Hunger
    hunger_max: int = 100
    hunger_decay_per_tick: int = 3
    hunger_auto_eat_threshold: int = 80
    hunger_eat_restore: int = 15
    hunger_eat_raw_restore: int = 5
    hunger_starve_coin_penalty: int = 10

    # Thirst
    thirst_decay_per_tick: int = 3
    thirst_auto_drink_threshold: int = 80
    thirst_drink_restore: int = 15
    thirst_dehydration_coin_penalty: int = 10
    passive_water_per_tick: int = 0

    # Foraging
    roles: list = field(
        default_factory=lambda: ["flour_forager", "water_forager", "baker"]
    )
    forage_skill_by_role: dict = field(
        default_factory=lambda: {
            "flour_forager": {"flour": 4, "water": 1},
            "water_forager": {"flour": 1, "water": 4},
            "baker": {"flour": 1, "water": 1},
        }
    )

    # Inventory
    inventory_cap: int = 100

    # Baking
    bake_cost: dict = field(default_factory=lambda: {"flour": 3, "water": 3})
    bake_yield: int = 2
    bake_baker_yield: int = 3

    # Spoilage
    bread_spoil_interval: int = 6
    bread_spoil_amount: int = 1

    # Brain
    context_window: int = 16000
    memory_max: int = 1000

    # Perception
    state_board_length: int = 10
    state_interactions_length: int = 10
    state_ledger_length: int = 10

    # Role descriptions
    role_descriptions: dict = field(
        default_factory=lambda: {
            "flour_forager": "You automatically forage and bake each tick. Your foraging yields vary — you produce more of some resources than others. Trade to get what you're short on.",
            "water_forager": "You automatically forage and bake each tick. Your foraging yields vary — you produce more of some resources than others. Trade to get what you're short on.",
        }
    )

    seed: int | None = None

    raw_cfg: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_file(cls) -> ScenarioConfig:
        cfg = load()
        generic_desc = "Your foraging yields vary — you produce more of some resources than others. Trade to get what you're short on."
        return cls(
            starting_coins=get(cfg, "starting", "coins", default=500),
            starting_flour=get(cfg, "starting", "flour", default=0),
            starting_water=get(cfg, "starting", "water", default=0),
            starting_bread=get(cfg, "starting", "bread", default=5),
            starting_hunger=get(cfg, "starting", "hunger", default=100),
            starting_thirst=get(cfg, "starting", "thirst", default=100),
            energy_max=get(cfg, "economy", "max_coins", default=1000),
            energy_cost_flat=get(
                cfg, "economy", "cost_flat", default={"update_soul": 5}
            ),
            energy_gain=get(
                cfg, "economy", "gain", default={"referenced": 10, "dm_received": 5}
            ),
            board_max_posts=get(cfg, "board", "max_posts", default=30),
            board_max_post_length=get(cfg, "board", "max_post_length", default=200),
            hunger_max=get(cfg, "hunger", "max", default=100),
            hunger_decay_per_tick=get(cfg, "hunger", "decay_per_tick", default=3),
            hunger_auto_eat_threshold=get(
                cfg, "hunger", "auto_eat_threshold", default=80
            ),
            hunger_eat_restore=get(cfg, "hunger", "eat_restore", default=15),
            hunger_eat_raw_restore=get(cfg, "hunger", "eat_raw_restore", default=5),
            hunger_starve_coin_penalty=get(
                cfg, "hunger", "starve_coin_penalty", default=10
            ),
            thirst_decay_per_tick=get(cfg, "thirst", "decay_per_tick", default=3),
            thirst_auto_drink_threshold=get(
                cfg, "thirst", "auto_drink_threshold", default=80
            ),
            thirst_drink_restore=get(cfg, "thirst", "drink_restore", default=15),
            thirst_dehydration_coin_penalty=get(
                cfg, "thirst", "dehydration_coin_penalty", default=10
            ),
            passive_water_per_tick=get(
                cfg, "thirst", "passive_water_per_tick", default=0
            ),
            roles=get(
                cfg,
                "foraging",
                "roles",
                default=["flour_forager", "water_forager", "baker"],
            ),
            forage_skill_by_role=get(
                cfg,
                "foraging",
                "skill_by_role",
                default={
                    "flour_forager": {"flour": 4, "water": 1},
                    "water_forager": {"flour": 1, "water": 4},
                    "baker": {"flour": 1, "water": 1},
                },
            ),
            inventory_cap=get(cfg, "inventory", "cap", default=100),
            bake_cost=get(
                cfg, "baking", "cost", default={"flour": 3, "water": 3}
            ),
            bake_yield=get(cfg, "baking", "yield", default=2),
            bake_baker_yield=get(cfg, "baking", "baker_yield", default=3),
            bread_spoil_interval=get(cfg, "spoilage", "interval", default=6),
            bread_spoil_amount=get(cfg, "spoilage", "amount", default=1),
            context_window=get(cfg, "brain", "context_window", default=16000),
            memory_max=get(cfg, "brain", "memory_max", default=1000),
            state_board_length=get(
                cfg, "perception", "board_length", default=10
            ),
            state_interactions_length=get(
                cfg, "perception", "interactions_length", default=10
            ),
            state_ledger_length=get(
                cfg, "perception", "ledger_length", default=10
            ),
            role_descriptions=get(
                cfg,
                "roles",
                "descriptions",
                default={
                    "flour_forager": generic_desc,
                    "water_forager": generic_desc,
                },
            ),
            seed=get(cfg, "seed", default=None),
            raw_cfg=cfg,
        )


_current: ScenarioConfig = ScenarioConfig.from_file()


def get_config() -> ScenarioConfig:
    """Return the current scenario configuration."""
    return _current


def reload() -> None:
    """Re-read config.json and update the module-level config instance."""
    global _current
    _current = ScenarioConfig.from_file()


# Personality traits
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

_available_traits: set[str] = set(TRAITS)


def assign_traits(n: int = 2) -> list[str]:
    if len(_available_traits) < n:
        _available_traits.update(TRAITS)
    chosen = _random.sample(sorted(_available_traits), n)
    _available_traits.difference_update(chosen)
    return chosen


def register_components(store) -> None:
    """Register all bread-economy components on a ComponentStore."""
    from scenarios.bread_economy.components import AgentInfo
    store.register(AgentInfo)
