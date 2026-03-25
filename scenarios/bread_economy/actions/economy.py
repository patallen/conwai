from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from conwai.engine import TickNumber
from scenarios.bread_economy.actions.helpers import _capped_add
from scenarios.bread_economy.components import Economy, Inventory
from scenarios.bread_economy.perception import BreadPerceptionBuilder

if TYPE_CHECKING:
    from conwai.world import World

log = logging.getLogger("conwai")

VALID_RESOURCES = ("coins", "flour", "water", "bread")


class OfferBook:
    """Manages pending trade offers between agents."""

    def __init__(self, expiry: int = 12):
        self.expiry = expiry
        self._next_id = 1
        self._offers: dict[int, dict] = {}

    def expire(self, tick: int) -> None:
        expired = [
            oid for oid, o in self._offers.items() if tick - o["tick"] >= self.expiry
        ]
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

    def offers_for(self, handle: str, tick: int) -> list[tuple[int, dict]]:
        """Return all pending offers directed at this agent."""
        return [
            (oid, o) for oid, o in self._offers.items()
            if o["to"] == handle and tick - o["tick"] < self.expiry
        ]


def _pay(entity_id: str, world: World, args: dict) -> str:
    to = args.get("to", "").lstrip("@")
    amount = args.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return "invalid amount"
    if amount <= 0:
        return "amount must be positive"
    eco = world.get(entity_id, Economy)
    if amount > eco.coins:
        return f"not enough coins to pay {amount} (have {int(eco.coins)})"
    alive = set(world.entities())
    if to not in alive:
        return f"unknown agent: {to}"
    if to == entity_id:
        return "cannot pay yourself"
    with world.mutate(entity_id, Economy) as eco:
        eco.coins -= amount
    with world.mutate(to, Economy) as other_eco:
        other_eco.coins += amount
    perception = world.get_resource(BreadPerceptionBuilder)
    perception.notify(entity_id, f"-{amount} coins (paid to @{to})")
    perception.notify(to, f"+{amount} coins (payment from @{entity_id})")
    log.info(f"[{entity_id}] paid {amount} coins to {to}")
    return f"paid {amount} coins to {to}"


def _give(entity_id: str, world: World, args: dict) -> str:
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
    inv = world.get(entity_id, Inventory)
    if amount > getattr(inv, resource):
        return f"not enough {resource} to give {amount} (have {getattr(inv, resource)})"
    alive = set(world.entities())
    if to not in alive:
        return f"unknown agent: {to}"
    if to == entity_id:
        return "cannot give to yourself"
    with world.mutate(entity_id, Inventory) as inv:
        setattr(inv, resource, getattr(inv, resource) - amount)
    with world.mutate(to, Inventory) as other_inv:
        _capped_add(other_inv, resource, amount)
    perception = world.get_resource(BreadPerceptionBuilder)
    perception.notify(to, f"received {amount} {resource} from @{entity_id}")
    log.info(f"[{entity_id}] gave {amount} {resource} to {to}")
    return f"gave {amount} {resource} to {to}"


def make_offer_handlers(offer_book: OfferBook | None = None):
    """Return (_offer, _accept) handler functions closed over the given OfferBook."""
    if offer_book is None:
        offer_book = OfferBook()

    def _offer(entity_id: str, world: World, args: dict) -> str:
        tick = world.get_resource(TickNumber).value
        offer_book.expire(tick)

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
        if to == entity_id:
            return "cannot trade with yourself"
        alive = set(world.entities())
        if to not in alive:
            return f"unknown agent: {to}"

        # Check the offerer actually has the resources
        if give_type == "coins":
            eco = world.get(entity_id, Economy)
            if give_amount > eco.coins:
                return f"not enough coins (have {int(eco.coins)})"
        else:
            inv = world.get(entity_id, Inventory)
            if give_amount > getattr(inv, give_type):
                return f"not enough {give_type} (have {getattr(inv, give_type)})"

        # Max 3 pending offers per agent
        if offer_book.count_by_agent(entity_id) >= 3:
            return "you already have 3 pending offers. Wait for them to be accepted or expire."

        oid = offer_book.create(
            {
                "from": entity_id,
                "to": to,
                "give_type": give_type,
                "give_amount": give_amount,
                "want_type": want_type,
                "want_amount": want_amount,
                "tick": tick,
            }
        )

        perception = world.get_resource(BreadPerceptionBuilder)
        perception.notify(
            to,
            f"Trade offer #{oid} from @{entity_id}: "
            f"you give {want_amount} {want_type}, you receive {give_amount} {give_type}. "
            f"Use accept(offer_id={oid}) to accept.",
        )

        log.info(
            f"[{entity_id}] offer #{oid} to {to}: {give_amount} {give_type} for {want_amount} {want_type}"
        )
        return (
            f"Offer sent to @{to}: {give_amount} {give_type} for {want_amount} {want_type}. Expires in {offer_book.expiry} ticks.",
            {"id": oid},
        )

    def _accept(entity_id: str, world: World, args: dict) -> str:
        tick = world.get_resource(TickNumber).value
        offer_book.expire(tick)

        try:
            oid = int(args.get("offer_id", 0))
        except (ValueError, TypeError):
            return f"Invalid offer_id: {args.get('offer_id')}. Use the numeric offer ID (e.g. 5)."
        offer = offer_book.get(oid)
        if not offer:
            return "That offer is no longer available."
        if offer["to"] != entity_id:
            return "That offer is not for you."

        offerer = offer["from"]
        give_type = offer["give_type"]
        give_amount = offer["give_amount"]
        want_type = offer["want_type"]
        want_amount = offer["want_amount"]

        # Verify offerer still has resources
        if give_type == "coins":
            off_eco = world.get(offerer, Economy)
            if give_amount > off_eco.coins:
                offer_book.remove(oid)
                return f"Trade failed: @{offerer} no longer has enough {give_type}."
        else:
            off_inv = world.get(offerer, Inventory)
            if give_amount > getattr(off_inv, give_type):
                offer_book.remove(oid)
                return f"Trade failed: @{offerer} no longer has enough {give_type}."

        # Verify accepter has the wanted resources
        if want_type == "coins":
            acc_eco = world.get(entity_id, Economy)
            if want_amount > acc_eco.coins:
                return f"You don't have enough coins (have {int(acc_eco.coins)}, need {want_amount})."
        else:
            acc_inv = world.get(entity_id, Inventory)
            if want_amount > getattr(acc_inv, want_type):
                return f"You don't have enough {want_type} (have {getattr(acc_inv, want_type)}, need {want_amount})."

        # Execute the swap atomically
        # Offerer gives give_type, accepter receives it
        if give_type == "coins":
            with world.mutate(offerer, Economy) as off_eco:
                off_eco.coins -= give_amount
            with world.mutate(entity_id, Economy) as acc_eco:
                acc_eco.coins += give_amount
        else:
            with world.mutate(offerer, Inventory) as off_inv:
                setattr(off_inv, give_type, getattr(off_inv, give_type) - give_amount)
            with world.mutate(entity_id, Inventory) as acc_inv:
                _capped_add(acc_inv, give_type, give_amount)

        # Accepter gives want_type, offerer receives it
        if want_type == "coins":
            with world.mutate(entity_id, Economy) as acc_eco:
                acc_eco.coins -= want_amount
            with world.mutate(offerer, Economy) as off_eco:
                off_eco.coins += want_amount
        else:
            with world.mutate(entity_id, Inventory) as acc_inv:
                setattr(acc_inv, want_type, getattr(acc_inv, want_type) - want_amount)
            with world.mutate(offerer, Inventory) as off_inv:
                _capped_add(off_inv, want_type, want_amount)

        offer_book.remove(oid)

        perception = world.get_resource(BreadPerceptionBuilder)
        perception.notify(
            offerer,
            f"Trade with @{entity_id}: gave {give_amount} {give_type}, received {want_amount} {want_type}",
        )
        perception.notify(
            entity_id,
            f"Trade with @{offerer}: received {give_amount} {give_type}, gave {want_amount} {want_type}",
        )

        if world.bus:
            from conwai.event_types import ActionExecuted
            world.bus.emit(ActionExecuted(
                entity=entity_id, action="trade",
                data={"id": oid, "with": offerer, "received_type": give_type,
                      "received_amount": give_amount, "gave_type": want_type,
                      "gave_amount": want_amount},
            ))
            world.bus.emit(ActionExecuted(
                entity=offerer, action="trade",
                data={"id": oid, "with": entity_id, "received_type": want_type,
                      "received_amount": want_amount, "gave_type": give_type,
                      "gave_amount": give_amount},
            ))
        log.info(
            f"[TRADE] #{oid}: {offerer} gave {give_amount} {give_type}, {entity_id} gave {want_amount} {want_type}"
        )
        return f"Trade complete: received {give_amount} {give_type} from {offerer}, gave {want_amount} {want_type}."

    return _offer, _accept
