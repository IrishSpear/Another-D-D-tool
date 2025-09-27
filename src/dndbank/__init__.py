"""DnDBank package mirroring the KidBank structure for tabletop parties."""

from __future__ import annotations

from typing import Any

from .account import CharacterAccount
from .compendium import EquipmentSummary, SRDCompendium
from .exceptions import (
    CharacterAlreadyExistsError,
    CharacterNotFoundError,
    InsufficientFundsError,
)
from .models import (
    AbilityScores,
    CharacterSheet,
    EventCategory,
    HitPointPool,
    InventoryItem,
    Transaction,
    TransactionType,
)
from .service import DnDBank


def create_app(config: dict[str, Any] | None = None):
    """Lazily import and construct the FastAPI application factory."""

    from .web import create_app as _create_app

    return _create_app(config)


__all__ = [
    "AbilityScores",
    "CharacterAccount",
    "CharacterAlreadyExistsError",
    "CharacterNotFoundError",
    "CharacterSheet",
    "DnDBank",
    "EquipmentSummary",
    "EventCategory",
    "HitPointPool",
    "InsufficientFundsError",
    "InventoryItem",
    "SRDCompendium",
    "Transaction",
    "TransactionType",
    "create_app",
]
