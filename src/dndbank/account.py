"""Character account logic for managing tabletop treasure."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, Optional, Tuple

from .exceptions import InsufficientFundsError
from .models import (
    AbilityScores,
    CharacterSheet,
    EventCategory,
    HitPointPool,
    InventoryItem,
    Transaction,
    TransactionType,
)
from .money import AmountLike, require_positive, to_decimal


class CharacterAccount:
    """Represents an adventurer's personal hoard."""

    __slots__ = ("name", "player", "_balance", "_transactions", "_sheet", "_inventory")

    @classmethod
    def from_serialized(cls, payload: Mapping[str, object]) -> "CharacterAccount":
        """Rehydrate an account from a JSON-compatible payload."""

        account = cls(
            str(payload["name"]),
            player=payload.get("player") or None,
            starting_gold=0,
        )
        account._balance = to_decimal(payload.get("balance", 0))
        account._transactions.clear()
        account._sheet = CharacterSheet.from_dict(payload.get("sheet", {}))
        account._inventory.clear()
        for raw_item in payload.get("inventory", []):
            item = InventoryItem.from_dict(raw_item)
            account._inventory[item.name.casefold()] = item
        for raw in payload.get("transactions", []):
            account._transactions.append(
                Transaction(
                    amount=to_decimal(raw["amount"]),
                    type=TransactionType(raw["type"]),
                    description=str(raw["description"]),
                    category=EventCategory(raw["category"]),
                    timestamp=datetime.fromisoformat(raw["timestamp"]),
                    metadata=dict(raw.get("metadata", {})),
                )
            )
        return account

    def __init__(
        self,
        name: str,
        *,
        player: str | None = None,
        starting_gold: AmountLike = 0,
        sheet: CharacterSheet | None = None,
    ) -> None:
        self.name = name
        self.player = player
        starting_value = to_decimal(starting_gold)
        require_positive(starting_value, allow_zero=True)
        self._balance: Decimal = starting_value
        self._transactions: list[Transaction] = []
        self._sheet = sheet or CharacterSheet()
        self._inventory: dict[str, InventoryItem] = {}

        if starting_value > Decimal("0"):
            self._log_transaction(
                starting_value,
                TransactionType.ADJUSTMENT,
                "Starting purse",
                EventCategory.MANUAL,
                {"source": "initial"},
                timestamp=datetime.now(timezone.utc),
            )

    @property
    def balance(self) -> Decimal:
        return self._balance

    @property
    def transactions(self) -> Tuple[Transaction, ...]:
        return tuple(self._transactions)

    @property
    def sheet(self) -> CharacterSheet:
        return self._sheet

    @property
    def inventory(self) -> Tuple[InventoryItem, ...]:
        return tuple(self._inventory.values())

    def earn(
        self,
        amount: AmountLike,
        description: str = "Treasure haul",
        *,
        category: EventCategory | None = None,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> Transaction:
        value = to_decimal(amount)
        require_positive(value)
        self._balance += value
        return self._log_transaction(
            value,
            TransactionType.EARN,
            description,
            category or EventCategory.LOOT,
            metadata,
        )

    def spend(
        self,
        amount: AmountLike,
        description: str = "Purchase",
        *,
        category: EventCategory | None = None,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> Transaction:
        value = to_decimal(amount)
        require_positive(value)
        self._ensure_sufficient(value)
        self._balance -= value
        return self._log_transaction(
            value,
            TransactionType.SPEND,
            description,
            category or EventCategory.PURCHASE,
            metadata,
        )

    def transfer_to(
        self,
        other: "CharacterAccount",
        amount: AmountLike,
        description: str | None = None,
        *,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> tuple[Transaction, Transaction]:
        value = to_decimal(amount)
        require_positive(value)
        self._ensure_sufficient(value)
        self._balance -= value
        other._balance += value

        summary_out = description or f"Transfer to {other.name}"
        summary_in = description or f"Transfer from {self.name}"
        ts = datetime.now(timezone.utc)
        outbound = self._log_transaction(
            value,
            TransactionType.TRANSFER_OUT,
            summary_out,
            EventCategory.MANUAL,
            metadata,
            timestamp=ts,
        )
        inbound = other._log_transaction(
            value,
            TransactionType.TRANSFER_IN,
            summary_in,
            EventCategory.MANUAL,
            metadata,
            timestamp=ts,
        )
        return outbound, inbound

    def update_sheet(self, **fields: object) -> CharacterSheet:
        """Update the character sheet with supplied fields."""

        self._sheet.update(**fields)
        return self._sheet

    def set_ability_scores(self, **scores: int) -> AbilityScores:
        self._sheet.ability_scores = self._sheet.ability_scores.updated(**scores)
        return self._sheet.ability_scores

    def adjust_hit_points(self, delta: int, *, use_temporary: bool = True) -> HitPointPool:
        pool = self._sheet.hit_points.apply_delta(delta, use_temporary=use_temporary)
        self._sheet.hit_points = pool
        return pool

    def set_hit_points(
        self,
        *,
        maximum: int | None = None,
        current: int | None = None,
        temporary: int | None = None,
    ) -> HitPointPool:
        pool = self._sheet.hit_points.with_updates(
            maximum=maximum,
            current=current,
            temporary=temporary,
        )
        self._sheet.hit_points = pool
        return pool

    def list_inventory(self) -> Tuple[InventoryItem, ...]:
        return tuple(self._inventory.values())

    def add_inventory_item(
        self,
        name: str,
        *,
        quantity: int = 1,
        description: str | None = None,
        weight: float | None = None,
        value_gp: AmountLike | None = None,
        category: str | None = None,
        equipped: bool | None = None,
    ) -> InventoryItem:
        key = name.casefold()
        existing = self._inventory.get(key)
        if existing:
            new_quantity = existing.quantity + quantity
            updated = existing.with_quantity(new_quantity).with_updates(
                description=description,
                weight=weight,
                value_gp=value_gp,
                category=category,
                equipped=equipped,
            )
        else:
            updated = InventoryItem(
                name=name,
                quantity=quantity,
                description=description or "",
                weight=weight,
                value_gp=to_decimal(value_gp) if value_gp is not None else None,
                category=category,
                equipped=equipped or False,
            )
        self._inventory[key] = updated
        return updated

    def update_inventory_item(
        self,
        name: str,
        *,
        quantity: int | None = None,
        description: str | None = None,
        weight: float | None = None,
        value_gp: AmountLike | None = None,
        category: str | None = None,
        equipped: bool | None = None,
    ) -> InventoryItem:
        key = name.casefold()
        if key not in self._inventory:
            raise KeyError(f"{self.name} does not carry '{name}'.")
        item = self._inventory[key]
        updated = item
        if quantity is not None:
            updated = updated.with_quantity(quantity)
        updated = updated.with_updates(
            description=description,
            weight=weight,
            value_gp=value_gp,
            category=category,
            equipped=equipped,
        )
        self._inventory[key] = updated
        return updated

    def remove_inventory_item(self, name: str, *, quantity: int | None = None) -> None:
        key = name.casefold()
        if key not in self._inventory:
            raise KeyError(f"{self.name} does not carry '{name}'.")
        item = self._inventory[key]
        if quantity is None or quantity >= item.quantity:
            del self._inventory[key]
        else:
            self._inventory[key] = item.with_quantity(item.quantity - quantity)

    def _ensure_sufficient(self, amount: Decimal) -> None:
        if self._balance < amount:
            raise InsufficientFundsError(
                f"{self.name} lacks sufficient gold (needs {amount}, has {self._balance})."
            )

    def _log_transaction(
        self,
        amount: Decimal,
        type_: TransactionType,
        description: str,
        category: EventCategory,
        metadata: Optional[Mapping[str, str]] = None,
        *,
        timestamp: datetime | None = None,
    ) -> Transaction:
        record = Transaction(
            amount=amount,
            type=type_,
            description=description,
            category=category,
            timestamp=timestamp or datetime.now(timezone.utc),
            metadata=dict(metadata or {}),
        )
        self._transactions.append(record)
        return record

    def summary(self) -> str:
        owner = f" (Player: {self.player})" if self.player else ""
        return f"{self.name}{owner} — {self._balance} gp"

    def to_serialized(self) -> dict[str, object]:
        return {
            "name": self.name,
            "player": self.player,
            "balance": str(self._balance),
            "sheet": self._sheet.as_dict(),
            "inventory": [item.as_dict() for item in self._inventory.values()],
            "transactions": [entry.as_dict() for entry in self._transactions],
        }
