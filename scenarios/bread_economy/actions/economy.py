from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scenarios.bread_economy.actions.helpers import _capped_add
from scenarios.bread_economy.components import Economy, Inventory

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext

log = logging.getLogger("conwai")

VALID_RESOURCES = ("coins", "flour", "water", "bread")


class OfferBook:
    """Manages pending trade offers between agents."""

    def __init__(self, expiry: int = 12):
        self.expiry = expiry
        self._next_id = 1
        self._offers: dict[int, dict] = {}

    def expire(self, tick: int) -> None:
        expired = [oid for oid, o in self._offers.items() if tick - o["tick"] >= self.expiry]
        for oid in expired:
            del self._offers[oid]

    def create(self, data: dict) -> int:
        oid = self._next_id
        self._next_id += 1
        self._offers[oid] = data
        return oid

    def get(self, oid: int) -> dict | None:
        return self._offers.get(oid)

    def remove(self, oid: int) -> None:
        self._offers.pop(oid, None)

    def count_by_agent(self, handle: str) -> int:
        return sum(1 for o in self._offers.values() if o["from"] == handle)


def _pay(agent: Agent, ctx: TickContext, args: dict) -> str:
    to = args.get("to", "").lstrip("@")
    amount = args.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return "invalid amount"
    if amount <= 0:
        return "amount must be positive"
    eco = ctx.store.get(agent.handle, Economy)
    if amount > eco.coins:
        return f"not enough coins to pay {amount} (have {int(eco.coins)})"
    if not ctx.pool:
        return "payment unavailable"
    other = ctx.pool.by_handle(to)
    if not other:
        return f"unknown agent: {to}"
    if to == agent.handle:
        return "cannot pay yourself"
    eco.coins -= amount
    ctx.store.set(agent.handle, eco)
    other_eco = ctx.store.get(to, Economy)
    other_eco.coins += amount
    ctx.store.set(to, other_eco)
    if ctx.perception:
        ctx.perception.notify(agent.handle, f"-{amount} coins (paid to @{to})")
        ctx.perception.notify(to, f"+{amount} coins (payment from @{agent.handle})")
    ctx.events.log(agent.handle, "payment", {"to": to, "amount": amount})
    log.info(f"[{agent.handle}] paid {amount} coins to {to}")
    return f"paid {amount} coins to {to}"


def _give(agent: Agent, ctx: TickContext, args: dict) -> str:
    resource = args.get("resource", "")
    to = args.get("to", "").lstrip("@")
    amount = args.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return "invalid amount"
    if amount <= 0:
        return "amount must be positive"
    if resource not in ("flour", "water", "bread"):
        return f"invalid resource: {resource}. Must be flour, water, or bread."
    inv = ctx.store.get(agent.handle, Inventory)
    if amount > getattr(inv, resource):
        return f"not enough {resource} to give {amount} (have {getattr(inv, resource)})"
    if not ctx.pool:
        return "giving unavailable"
    other = ctx.pool.by_handle(to)
    if not other:
        return f"unknown agent: {to}"
    if to == agent.handle:
        return "cannot give to yourself"
    setattr(inv, resource, getattr(inv, resource) - amount)
    ctx.store.set(agent.handle, inv)
    other_inv = ctx.store.get(to, Inventory)
    _capped_add(other_inv, resource, amount)
    ctx.store.set(to, other_inv)
    if ctx.perception:
        ctx.perception.notify(to, f"received {amount} {resource} from @{agent.handle}")
    ctx.events.log(
        agent.handle, "give", {"to": to, "resource": resource, "amount": amount}
    )
    log.info(f"[{agent.handle}] gave {amount} {resource} to {to}")
    return f"gave {amount} {resource} to {to}"


def make_offer_handlers(offer_book: OfferBook | None = None):
    """Return (_offer, _accept) handler functions closed over the given OfferBook."""
    if offer_book is None:
        offer_book = OfferBook()

    def _offer(agent: Agent, ctx: TickContext, args: dict) -> str:
        offer_book.expire(ctx.tick)

        to = args.get("to", "").lstrip("@")
        give_type = args.get("give_type", "")
        give_amount = int(args.get("give_amount", 0))
        want_type = args.get("want_type", "")
        want_amount = int(args.get("want_amount", 0))

        if not to or not give_type or not want_type:
            return "missing fields: to, give_type, give_amount, want_type, want_amount"
        if give_type not in VALID_RESOURCES or want_type not in VALID_RESOURCES:
            return f"invalid resource. Must be one of: {', '.join(VALID_RESOURCES)}"
        if give_amount <= 0 or want_amount <= 0:
            return "amounts must be positive"
        if to == agent.handle:
            return "cannot trade with yourself"
        if not ctx.pool or not ctx.pool.by_handle(to):
            return f"unknown agent: {to}"

        # Check the offerer actually has the resources
        if give_type == "coins":
            eco = ctx.store.get(agent.handle, Economy)
            if give_amount > eco.coins:
                return f"not enough coins (have {int(eco.coins)})"
        else:
            inv = ctx.store.get(agent.handle, Inventory)
            if give_amount > getattr(inv, give_type):
                return f"not enough {give_type} (have {getattr(inv, give_type)})"

        # Max 3 pending offers per agent
        if offer_book.count_by_agent(agent.handle) >= 3:
            return "you already have 3 pending offers. Wait for them to be accepted or expire."

        oid = offer_book.create({
            "from": agent.handle, "to": to,
            "give_type": give_type, "give_amount": give_amount,
            "want_type": want_type, "want_amount": want_amount,
            "tick": ctx.tick,
        })

        if ctx.perception:
            ctx.perception.notify(
                to,
                f"Trade offer #{oid} from @{agent.handle}: {give_amount} {give_type} for {want_amount} {want_type}. Use accept(offer_id={oid}) to accept.",
            )

        ctx.events.log(agent.handle, "offer", {
            "id": oid, "to": to, "give_type": give_type, "give_amount": give_amount,
            "want_type": want_type, "want_amount": want_amount,
        })
        log.info(f"[{agent.handle}] offer #{oid} to {to}: {give_amount} {give_type} for {want_amount} {want_type}")
        return f"Offer #{oid} sent to {to}: {give_amount} {give_type} for {want_amount} {want_type}. Expires in {offer_book.expiry} ticks."

    def _accept(agent: Agent, ctx: TickContext, args: dict) -> str:
        offer_book.expire(ctx.tick)

        try:
            oid = int(args.get("offer_id", 0))
        except (ValueError, TypeError):
            return f"Invalid offer_id: {args.get('offer_id')}. Use the numeric offer ID (e.g. 5)."
        offer = offer_book.get(oid)
        if not offer:
            return f"Offer #{oid} not found or expired."
        if offer["to"] != agent.handle:
            return f"Offer #{oid} is not for you."

        offerer = offer["from"]
        give_type = offer["give_type"]
        give_amount = offer["give_amount"]
        want_type = offer["want_type"]
        want_amount = offer["want_amount"]

        # Verify offerer still has resources
        if give_type == "coins":
            off_eco = ctx.store.get(offerer, Economy)
            if give_amount > off_eco.coins:
                offer_book.remove(oid)
                return f"Offer #{oid} failed: {offerer} no longer has enough {give_type}."
        else:
            off_inv = ctx.store.get(offerer, Inventory)
            if give_amount > getattr(off_inv, give_type):
                offer_book.remove(oid)
                return f"Offer #{oid} failed: {offerer} no longer has enough {give_type}."

        # Verify accepter has the wanted resources
        if want_type == "coins":
            acc_eco = ctx.store.get(agent.handle, Economy)
            if want_amount > acc_eco.coins:
                return f"You don't have enough coins (have {int(acc_eco.coins)}, need {want_amount})."
        else:
            acc_inv = ctx.store.get(agent.handle, Inventory)
            if want_amount > getattr(acc_inv, want_type):
                return f"You don't have enough {want_type} (have {getattr(acc_inv, want_type)}, need {want_amount})."

        # Execute the swap atomically
        # Offerer gives give_type, accepter receives it
        if give_type == "coins":
            off_eco = ctx.store.get(offerer, Economy)
            off_eco.coins -= give_amount
            ctx.store.set(offerer, off_eco)
            acc_eco = ctx.store.get(agent.handle, Economy)
            acc_eco.coins += give_amount
            ctx.store.set(agent.handle, acc_eco)
        else:
            off_inv = ctx.store.get(offerer, Inventory)
            setattr(off_inv, give_type, getattr(off_inv, give_type) - give_amount)
            ctx.store.set(offerer, off_inv)
            acc_inv = ctx.store.get(agent.handle, Inventory)
            _capped_add(acc_inv, give_type, give_amount)
            ctx.store.set(agent.handle, acc_inv)

        # Accepter gives want_type, offerer receives it
        if want_type == "coins":
            acc_eco = ctx.store.get(agent.handle, Economy)
            acc_eco.coins -= want_amount
            ctx.store.set(agent.handle, acc_eco)
            off_eco = ctx.store.get(offerer, Economy)
            off_eco.coins += want_amount
            ctx.store.set(offerer, off_eco)
        else:
            acc_inv = ctx.store.get(agent.handle, Inventory)
            setattr(acc_inv, want_type, getattr(acc_inv, want_type) - want_amount)
            ctx.store.set(agent.handle, acc_inv)
            off_inv = ctx.store.get(offerer, Inventory)
            _capped_add(off_inv, want_type, want_amount)
            ctx.store.set(offerer, off_inv)

        offer_book.remove(oid)

        if ctx.perception:
            ctx.perception.notify(offerer, f"Offer #{oid} accepted by @{agent.handle}: gave {give_amount} {give_type}, received {want_amount} {want_type}")
            ctx.perception.notify(agent.handle, f"Accepted offer #{oid} from @{offerer}: received {give_amount} {give_type}, gave {want_amount} {want_type}")

        ctx.events.log(agent.handle, "trade", {
            "id": oid, "with": offerer,
            "received_type": give_type, "received_amount": give_amount,
            "gave_type": want_type, "gave_amount": want_amount,
        })
        ctx.events.log(offerer, "trade", {
            "id": oid, "with": agent.handle,
            "received_type": want_type, "received_amount": want_amount,
            "gave_type": give_type, "gave_amount": give_amount,
        })
        log.info(f"[TRADE] #{oid}: {offerer} gave {give_amount} {give_type}, {agent.handle} gave {want_amount} {want_type}")
        return f"Trade complete: received {give_amount} {give_type} from {offerer}, gave {want_amount} {want_type}."

    return _offer, _accept
