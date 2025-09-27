"""Core dataclasses and enums used across the DnDBank domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Mapping


class TransactionType(str, Enum):
    """Classifies the type of movement recorded in the ledger."""

    EARN = "earn"
    SPEND = "spend"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    ADJUSTMENT = "adjustment"


class EventCategory(str, Enum):
    """Categorises how gold was gained or spent."""

    QUEST = "quest"
    LOOT = "loot"
    PURCHASE = "purchase"
    DOWNTIME = "downtime"
    MANUAL = "manual"


@dataclass(frozen=True)
class Transaction:
    """Immutable record of a single ledger entry."""

    amount: Decimal
    type: TransactionType
    description: str
    category: EventCategory
    timestamp: datetime
    metadata: Mapping[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, str]:
        return {
            "amount": str(self.amount),
            "type": self.type.value,
            "description": self.description,
            "category": self.category.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": dict(self.metadata),
        }
