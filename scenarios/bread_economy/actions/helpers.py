from __future__ import annotations

from scenarios.bread_economy.config import get_config


def _capped_add(inv: dict, resource: str, amount: int) -> int:
    """Add to inventory respecting cap. Returns actual amount added."""
    cap = get_config().inventory_cap
    actual = min(amount, max(0, cap - inv.get(resource, 0)))
    inv[resource] = inv.get(resource, 0) + actual
    return actual


def charge(store, handle: str, amount: int, reason: str) -> str | None:
    """Deduct coins. Returns error string if insufficient, None on success."""
    eco = store.get(handle, "economy")
    if amount > eco["coins"]:
        return f"not enough coins for {reason} ({amount} needed, have {int(eco['coins'])})"
    eco["coins"] -= amount
    store.set(handle, "economy", eco)
    return None
