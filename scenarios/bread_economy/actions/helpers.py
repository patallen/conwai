from __future__ import annotations

from typing import TYPE_CHECKING

from scenarios.bread_economy.components import Economy, Inventory
from scenarios.bread_economy.config import get_config
from scenarios.bread_economy.systems import deposit_to_treasury

if TYPE_CHECKING:
    from conwai.world import World


def _capped_add(inv: Inventory, resource: str, amount: int) -> int:
    """Add to inventory respecting cap. Returns actual amount added."""
    cap = get_config().inventory_cap
    current = getattr(inv, resource)
    actual = min(amount, max(0, cap - current))
    setattr(inv, resource, current + actual)
    return actual


def charge(world: World, entity_id: str, amount: int, reason: str) -> str | None:
    """Deduct coins. Returns error string if insufficient, None on success."""
    eco = world.get(entity_id, Economy)
    if amount > eco.coins:
        return f"not enough coins for {reason} ({amount} needed, have {int(eco.coins)})"
    with world.mutate(entity_id, Economy) as eco:
        eco.coins -= amount
    deposit_to_treasury(world, amount)
    return None
