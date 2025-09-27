"""Character account logic for managing tabletop treasure."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, Optional, Tuple

from .exceptions import InsufficientFundsError
from .models import EventCategory, Transaction, TransactionType
from .money import AmountLike, require_positive, to_decimal


class CharacterAccount:
    """Represents an adventurer's personal hoard."""

    __slots__ = ("name", "player", "_balance", "_transactions")

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
    ) -> None:
        self.name = name
        self.player = player
        starting_value = to_decimal(starting_gold)
        require_positive(starting_value, allow_zero=True)
        self._balance: Decimal = starting_value
        self._transactions: list[Transaction] = []

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
            "transactions": [entry.as_dict() for entry in self._transactions],
        }
