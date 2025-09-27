"""Core dataclasses and enums used across the DnDBank domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Mapping, MutableMapping

from .money import AmountLike, to_decimal


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


@dataclass(frozen=True)
class AbilityScores:
    """Represents a standard D&D ability score block."""

    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10

    def __post_init__(self) -> None:
        for name, value in self.as_dict().items():
            if not 1 <= value <= 30:
                raise ValueError(
                    f"Ability score '{name}' must be between 1 and 30 (got {value})."
                )

    def modifier(self, ability: str) -> int:
        """Return the D&D modifier for the requested ability name."""

        lookup = self.as_dict()
        try:
            score = lookup[ability.lower()]
        except KeyError as exc:
            raise KeyError(f"Unknown ability '{ability}'.") from exc
        return (score - 10) // 2

    def updated(self, **scores: int) -> "AbilityScores":
        """Return a new ``AbilityScores`` with the provided overrides."""

        normalized: dict[str, int] = self.as_dict()
        for key, value in scores.items():
            lowered = key.lower()
            if lowered not in normalized:
                raise KeyError(f"Unknown ability '{key}'.")
            normalized[lowered] = int(value)
        return AbilityScores(**normalized)

    def as_dict(self) -> dict[str, int]:
        return {
            "strength": self.strength,
            "dexterity": self.dexterity,
            "constitution": self.constitution,
            "intelligence": self.intelligence,
            "wisdom": self.wisdom,
            "charisma": self.charisma,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, int]) -> "AbilityScores":
        defaults = cls().as_dict()
        overrides = {key.lower(): int(value) for key, value in payload.items()}
        merged = {name: overrides.get(name, default) for name, default in defaults.items()}
        return cls(**merged)


@dataclass(frozen=True)
class HitPointPool:
    """Tracks a character's hit point pools."""

    maximum: int = 1
    current: int = 1
    temporary: int = 0

    def __post_init__(self) -> None:
        if self.maximum < 0:
            raise ValueError("Maximum hit points cannot be negative.")
        if self.current < 0 or self.temporary < 0:
            raise ValueError("Hit point values cannot be negative.")
        if self.current > self.maximum:
            object.__setattr__(self, "current", self.maximum)

    def apply_delta(self, delta: int, *, use_temporary: bool = True) -> "HitPointPool":
        """Return a new pool after applying healing or damage."""

        current = self.current
        temporary = self.temporary
        if delta >= 0:
            current = min(self.maximum, current + delta)
        else:
            damage = -delta
            if use_temporary and temporary > 0:
                absorbed = min(temporary, damage)
                temporary -= absorbed
                damage -= absorbed
            current = max(0, current - damage)
        return HitPointPool(maximum=self.maximum, current=current, temporary=temporary)

    def with_updates(
        self,
        *,
        maximum: int | None = None,
        current: int | None = None,
        temporary: int | None = None,
    ) -> "HitPointPool":
        return HitPointPool(
            maximum=self.maximum if maximum is None else maximum,
            current=self.current if current is None else current,
            temporary=self.temporary if temporary is None else temporary,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "maximum": self.maximum,
            "current": self.current,
            "temporary": self.temporary,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, int]) -> "HitPointPool":
        return cls(
            maximum=int(payload.get("maximum", 1)),
            current=int(payload.get("current", payload.get("maximum", 1))),
            temporary=int(payload.get("temporary", 0)),
        )


@dataclass
class CharacterSheet:
    """Stores the role-playing details for a character."""

    ancestry: str | None = None
    character_class: str | None = None
    background: str | None = None
    alignment: str | None = None
    level: int = 1
    experience: int = 0
    proficiency_bonus: int = 2
    ability_scores: AbilityScores = field(default_factory=AbilityScores)
    hit_points: HitPointPool = field(default_factory=HitPointPool)
    inspiration: bool = False
    passive_perception: int | None = None
    notes: str | None = None

    def update(self, **fields: object) -> "CharacterSheet":
        """Update sheet fields in-place and return ``self`` for chaining."""

        for key, value in fields.items():
            if key == "ability_scores":
                if isinstance(value, AbilityScores):
                    self.ability_scores = value
                elif isinstance(value, Mapping):
                    self.ability_scores = self.ability_scores.updated(**value)
                else:
                    raise TypeError("ability_scores must be an AbilityScores or mapping")
            elif key == "hit_points":
                if isinstance(value, HitPointPool):
                    self.hit_points = value
                elif isinstance(value, Mapping):
                    self.hit_points = self.hit_points.with_updates(
                        maximum=value.get("maximum"),
                        current=value.get("current"),
                        temporary=value.get("temporary"),
                    )
                else:
                    raise TypeError("hit_points must be a HitPointPool or mapping")
            elif hasattr(self, key):
                setattr(self, key, value)
            else:
                raise AttributeError(f"Unknown sheet field '{key}'.")
        return self

    def as_dict(self) -> dict[str, object]:
        return {
            "ancestry": self.ancestry,
            "character_class": self.character_class,
            "background": self.background,
            "alignment": self.alignment,
            "level": self.level,
            "experience": self.experience,
            "proficiency_bonus": self.proficiency_bonus,
            "ability_scores": self.ability_scores.as_dict(),
            "hit_points": self.hit_points.as_dict(),
            "inspiration": self.inspiration,
            "passive_perception": self.passive_perception,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CharacterSheet":
        sheet = cls()
        data: MutableMapping[str, object] = dict(payload)
        abilities = data.pop("ability_scores", None)
        hit_points = data.pop("hit_points", None)
        sheet.update(**data)
        if abilities:
            sheet.ability_scores = AbilityScores.from_dict(abilities)
        if hit_points:
            sheet.hit_points = HitPointPool.from_dict(hit_points)
        return sheet


@dataclass(frozen=True)
class InventoryItem:
    """Represents a single entry on a character's inventory list."""

    name: str
    quantity: int = 1
    description: str = ""
    weight: float | None = None
    value_gp: Decimal | None = None
    category: str | None = None
    equipped: bool = False

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Item quantity must be positive.")

    def with_quantity(self, quantity: int) -> "InventoryItem":
        if quantity <= 0:
            raise ValueError("Item quantity must be positive.")
        return InventoryItem(
            name=self.name,
            quantity=quantity,
            description=self.description,
            weight=self.weight,
            value_gp=self.value_gp,
            category=self.category,
            equipped=self.equipped,
        )

    def with_updates(
        self,
        *,
        description: str | None = None,
        weight: float | None = None,
        value_gp: AmountLike | None = None,
        category: str | None = None,
        equipped: bool | None = None,
    ) -> "InventoryItem":
        return InventoryItem(
            name=self.name,
            quantity=self.quantity,
            description=self.description if description is None else description,
            weight=self.weight if weight is None else weight,
            value_gp=self.value_gp if value_gp is None else to_decimal(value_gp),
            category=self.category if category is None else category,
            equipped=self.equipped if equipped is None else equipped,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "quantity": self.quantity,
            "description": self.description,
            "weight": self.weight,
            "value_gp": str(self.value_gp) if self.value_gp is not None else None,
            "category": self.category,
            "equipped": self.equipped,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "InventoryItem":
        value = payload.get("value_gp")
        parsed_value = None if value in (None, "") else to_decimal(value)  # type: ignore[arg-type]
        weight = payload.get("weight")
        parsed_weight = None if weight in (None, "") else float(weight)
        return cls(
            name=str(payload["name"]),
            quantity=int(payload.get("quantity", 1)),
            description=str(payload.get("description", "")),
            weight=parsed_weight,
            value_gp=parsed_value,
            category=(payload.get("category") or None),
            equipped=bool(payload.get("equipped", False)),
        )
