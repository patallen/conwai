#!/usr/bin/env python3
"""Economy balance calculator. Reads config.json and prints sustainability metrics."""

import json
from pathlib import Path


def load_config():
    return json.loads(Path("config.json").read_text())

def sim_survival(max_val, decay, threshold, restore, supply_per_tick):
    """Simulate ticks until death given a supply rate. Returns ticks survived, consumption rate."""
    val = max_val
    consumed = 0
    stock = 0.0
    for tick in range(1, 5000):
        stock += supply_per_tick
        val -= decay
        if val <= threshold and stock >= 1:
            val = min(max_val, val + restore)
            stock -= 1
            consumed += 1
        if val <= 0:
            return tick, consumed / tick if tick > 0 else 0
    return 5000, consumed / 5000

def main():
    c = load_config()

    decay_h = c["hunger_decay_per_tick"]
    decay_t = c["thirst_decay_per_tick"]
    max_h = c["hunger_max"]
    threshold_h = c["hunger_auto_eat_threshold"]
    restore_bread = c["hunger_eat_restore"]
    restore_raw = c["hunger_eat_raw_restore"]
    threshold_t = c["thirst_auto_drink_threshold"]
    restore_water = c["thirst_drink_restore"]
    bake_cost = c["bake_cost"]
    bake_yield = c["bake_yield"]
    spoil_interval = c["bread_spoil_interval"]
    spoil_amount = c["bread_spoil_amount"]
    skills = c["forage_skill_by_role"]

    print("=" * 60)
    print("ECONOMY BALANCE CALCULATOR")
    print("=" * 60)

    # Basic survival math
    ticks_to_starve = max_h // decay_h
    ticks_to_dehydrate = max_h // decay_t
    print("\n--- Survival Bars ---")
    print(f"Hunger: {max_h} max, -{decay_h}/tick, eat threshold ≤{threshold_h}")
    print(f"  Ticks to starve (no food):    {ticks_to_starve}")
    print(f"  Bread restore: +{restore_bread}  Raw flour: +{restore_raw}")
    print(f"Thirst: {max_h} max, -{decay_t}/tick, drink threshold ≤{threshold_t}")
    print(f"  Ticks to dehydrate (no water): {ticks_to_dehydrate}")
    print(f"  Water restore: +{restore_water}")

    # Consumption rates via simulation
    print("\n--- Consumption Rates (auto-eat/drink sim) ---")
    for food, restore, label in [("bread", restore_bread, "Bread"), ("flour", restore_raw, "Raw flour")]:
        _, rate = sim_survival(max_h, decay_h, threshold_h, restore, 99)
        print(f"  {label}: ~{rate:.2f}/tick to sustain hunger")
    _, water_rate = sim_survival(max_h, decay_t, threshold_t, restore_water, 99)
    print(f"  Water:  ~{water_rate:.2f}/tick to sustain thirst")

    # Per-role foraging
    # Agents spend ticks on DMs, inspecting, posting, etc. — not just foraging.
    # From actual run data: ~18% of actions are forages.
    # Foraging also blocks the whole tick, so it's a real trade-off.
    FORAGE_RATE = 0.20  # fraction of ticks spent foraging (estimate)
    print(f"\n--- Foraging (avg yield per tick, {FORAGE_RATE:.0%} forage rate) ---")
    roles = {}
    for role, sk in skills.items():
        avg_flour = sk["flour"] / 2 * FORAGE_RATE
        avg_water = sk["water"] / 2 * FORAGE_RATE
        roles[role] = {"flour": avg_flour, "water": avg_water}
        raw_flour = sk["flour"] / 2
        raw_water = sk["water"] / 2
        print(f"  {role:15s}: {avg_flour:.2f} flour, {avg_water:.2f} water  (raw: {raw_flour:.1f}, {raw_water:.1f} if 100%)")

    # Self-sufficiency per role (using raw eating)
    _, flour_rate = sim_survival(max_h, decay_h, threshold_h, restore_raw, 99)
    _, water_rate = sim_survival(max_h, decay_t, threshold_t, restore_water, 99)

    print("\n--- Self-Sufficiency (foraging every tick, raw eating) ---")
    for role, yields in roles.items():
        flour_surplus = yields["flour"] - flour_rate
        water_surplus = yields["water"] - water_rate
        status_h = "OK" if flour_surplus >= 0 else f"DEFICIT {flour_surplus:.2f}/tick"
        status_t = "OK" if water_surplus >= 0 else f"DEFICIT {water_surplus:.2f}/tick"
        print(f"  {role:15s}: hunger={status_h} (surplus {flour_surplus:+.2f} flour)")
        print(f"  {'':15s}  thirst={status_t} (surplus {water_surplus:+.2f} water)")

    # Baking economics
    print("\n--- Baking ---")
    print(f"  Cost: {bake_cost['flour']} flour + {bake_cost['water']} water")
    print(f"  Yield: {bake_yield} bread")
    raw_hunger = bake_cost["flour"] * restore_raw
    bread_hunger = bake_yield * restore_bread
    print(f"  Hunger from raw eating inputs: {raw_hunger} ({bake_cost['flour']} flour × {restore_raw})")
    print(f"  Hunger from baked bread:       {bread_hunger} ({bake_yield} bread × {restore_bread})")
    print(f"  Baking multiplier:             {bread_hunger/raw_hunger:.1f}x")
    print("  (water inputs don't help hunger, only thirst)")

    # Spoilage
    if spoil_interval > 0:
        spoil_rate = spoil_amount / spoil_interval
        print("\n--- Spoilage ---")
        print(f"  {spoil_amount} bread lost every {spoil_interval} ticks ({spoil_rate:.2f}/tick)")
        print(f"  Bread must be consumed within ~{spoil_interval} ticks or it rots")

    # System-level flows for a given population
    print("\n--- Population Flows (current: 6 flour, 6 water, 4 bakers) ---")
    n_flour, n_water, n_baker = 6, 6, 4
    total_flour_in = n_flour * roles["flour_forager"]["flour"] + n_water * roles["water_forager"]["flour"]
    total_water_in = n_flour * roles["flour_forager"]["water"] + n_water * roles["water_forager"]["water"]
    total_flour_consumed_self = (n_flour + n_water) * flour_rate
    total_water_consumed_self = (n_flour + n_water) * water_rate
    flour_available = total_flour_in - total_flour_consumed_self
    water_available = total_water_in - total_water_consumed_self
    max_bakes = min(flour_available / bake_cost["flour"], water_available / bake_cost["water"])
    bread_produced = max_bakes * bake_yield
    bread_needed_bakers = n_baker * flour_rate  # bakers eat bread instead of flour
    # Actually bakers need bread for hunger. Let's use bread consumption rate
    _, bread_rate = sim_survival(max_h, decay_h, threshold_h, restore_bread, 99)
    bread_needed_bakers = n_baker * bread_rate
    bread_surplus = bread_produced - bread_needed_bakers
    spoil_loss = (n_flour + n_water + n_baker) * spoil_rate if spoil_interval > 0 else 0

    print(f"  Flour produced:      {total_flour_in:.1f}/tick")
    print(f"  Water produced:      {total_water_in:.1f}/tick")
    print(f"  Flour self-consumed: {total_flour_consumed_self:.1f}/tick (foragers eating raw)")
    print(f"  Water self-consumed: {total_water_consumed_self:.1f}/tick (foragers drinking)")
    print(f"  Flour tradeable:     {flour_available:.1f}/tick")
    print(f"  Water tradeable:     {water_available:.1f}/tick")
    print(f"  Max bakes possible:  {max_bakes:.1f}/tick")
    print(f"  Bread produced:      {bread_produced:.1f}/tick")
    print(f"  Bread for bakers:    {bread_needed_bakers:.1f}/tick")
    print(f"  Bread surplus:       {bread_surplus:.1f}/tick (available for foragers)")
    if spoil_interval > 0:
        print(f"  Spoilage loss:       {spoil_loss:.1f}/tick")

    # Baker sustainability
    print("\n--- Baker Dependency ---")
    baker_flour_need = bake_cost["flour"] * bread_rate / bake_yield
    baker_water_need = bake_cost["water"] * bread_rate / bake_yield
    baker_sk = skills["baker"]
    baker_flour_self = baker_sk["flour"] / 2
    baker_water_self = baker_sk["water"] / 2
    baker_flour_deficit = baker_flour_need - baker_flour_self
    baker_water_deficit = baker_water_need - baker_water_self
    print(f"  Baker needs {baker_flour_need:.2f} flour/tick + {baker_water_need:.2f} water/tick to sustain via bread")
    print(f"  Baker forages: {baker_flour_self:.1f} flour, {baker_water_self:.1f} water")
    print(f"  Baker deficit: {baker_flour_deficit:.2f} flour, {baker_water_deficit:.2f} water (must trade for)")


if __name__ == "__main__":
    main()
