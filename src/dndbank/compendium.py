"""Utilities for loading reference data from the 5e SRD database repository."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .models import InventoryItem


@dataclass(frozen=True)
class EquipmentSummary:
    """Lightweight view of an equipment entry from the compendium."""

    index: str
    name: str
    category: str | None
    cost_gp: Decimal | None
    weight: float | None
    description: str

    def to_inventory_item(
        self,
        *,
        quantity: int = 1,
        equipped: bool | None = None,
    ) -> InventoryItem:
        """Convert the summary into an :class:`InventoryItem`."""

        return InventoryItem(
            name=self.name,
            quantity=quantity,
            description=self.description,
            weight=self.weight,
            value_gp=self.cost_gp,
            category=self.category,
            equipped=False if equipped is None else equipped,
        )


class SRDCompendium:
    """Helper for reading JSON data from ``5e-bits/5e-database`` checkouts."""

    #: Mapping of logical category names to the JSON files shipped in the
    #: ``5e-bits/5e-database`` repository. The default release targets the
    #: original 2014 System Reference Document, but the loader can point to any
    #: release folder under ``src/``.
    CATEGORY_FILES: Mapping[str, str] = {
        "ability-scores": "5e-SRD-Ability-Scores.json",
        "alignments": "5e-SRD-Alignments.json",
        "backgrounds": "5e-SRD-Backgrounds.json",
        "classes": "5e-SRD-Classes.json",
        "conditions": "5e-SRD-Conditions.json",
        "damage-types": "5e-SRD-Damage-Types.json",
        "equipment": "5e-SRD-Equipment.json",
        "equipment-categories": "5e-SRD-Equipment-Categories.json",
        "feats": "5e-SRD-Feats.json",
        "features": "5e-SRD-Features.json",
        "languages": "5e-SRD-Languages.json",
        "magic-items": "5e-SRD-Magic-Items.json",
        "magic-schools": "5e-SRD-Magic-Schools.json",
        "monsters": "5e-SRD-Monsters.json",
        "proficiencies": "5e-SRD-Proficiencies.json",
        "races": "5e-SRD-Races.json",
        "rules": "5e-SRD-Rules.json",
        "rule-sections": "5e-SRD-Rule-Sections.json",
        "skills": "5e-SRD-Skills.json",
        "spells": "5e-SRD-Spells.json",
        "subclasses": "5e-SRD-Subclasses.json",
        "subraces": "5e-SRD-Subraces.json",
        "traits": "5e-SRD-Traits.json",
        "weapon-properties": "5e-SRD-Weapon-Properties.json",
    }

    def __init__(self, repository_root: Path | str, *, release: str = "2014") -> None:
        root_path = Path(repository_root)
        data_dir = root_path / "src" / release
        if not data_dir.is_dir():
            raise FileNotFoundError(
                f"Could not locate SRD data in '{data_dir}'. "
                "Ensure you point to a 5e-bits/5e-database checkout."
            )
        self._data_dir = data_dir
        self.release = release
        self._cache: dict[str, Sequence[Mapping[str, object]]] = {}

    # ------------------------------------------------------------------
    # Generic loading helpers
    # ------------------------------------------------------------------
    @property
    def categories(self) -> tuple[str, ...]:
        """Return the supported categories available in the data set."""

        available: list[str] = []
        for name, filename in self.CATEGORY_FILES.items():
            if (self._data_dir / filename).is_file():
                available.append(name)
        return tuple(sorted(available))

    def _load_category(self, category: str) -> Sequence[Mapping[str, object]]:
        try:
            filename = self.CATEGORY_FILES[category]
        except KeyError as exc:
            raise KeyError(f"Unknown compendium category '{category}'.") from exc

        if category not in self._cache:
            path = self._data_dir / filename
            if not path.is_file():
                raise FileNotFoundError(
                    f"The '{category}' data file is missing ({path})."
                )
            with path.open("r", encoding="utf8") as fh:
                payload = json.load(fh)
            if not isinstance(payload, list):
                raise ValueError(
                    f"Unexpected payload for '{category}'. Expected a list of entries."
                )
            self._cache[category] = tuple(payload)
        return self._cache[category]

    def search(self, category: str, query: str) -> tuple[Mapping[str, object], ...]:
        """Return entries whose name or index contains the given query."""

        haystack = self._load_category(category)
        needle = query.casefold()
        matches = []
        for entry in haystack:
            name = str(entry.get("name", "")).casefold()
            index = str(entry.get("index", "")).casefold()
            if needle in name or needle in index:
                matches.append(entry)
        return tuple(matches)

    def get(self, category: str, key: str) -> Mapping[str, object] | None:
        """Look up a single entry by index or name."""

        lookup = key.casefold()
        for entry in self._load_category(category):
            if str(entry.get("index", "")).casefold() == lookup:
                return entry
            if str(entry.get("name", "")).casefold() == lookup:
                return entry
        return None

    # ------------------------------------------------------------------
    # Equipment-specific helpers
    # ------------------------------------------------------------------
    def search_equipment(self, query: str) -> tuple[EquipmentSummary, ...]:
        entries = self.search("equipment", query)
        return tuple(self._as_equipment_summary(entry) for entry in entries)

    def get_equipment(self, key: str) -> EquipmentSummary | None:
        entry = self.get("equipment", key)
        if not entry:
            return None
        return self._as_equipment_summary(entry)

    @staticmethod
    def _as_equipment_summary(entry: Mapping[str, object]) -> EquipmentSummary:
        category: str | None = None
        equipment_category = entry.get("equipment_category")
        if isinstance(equipment_category, Mapping):
            category = str(equipment_category.get("name")) if equipment_category.get("name") else None
        elif isinstance(entry.get("gear_category"), Mapping):
            gear = entry["gear_category"]
            category = str(gear.get("name")) if gear.get("name") else None

        weight_raw = entry.get("weight")
        weight: float | None
        try:
            weight = float(weight_raw) if weight_raw is not None else None
        except (TypeError, ValueError):
            weight = None

        cost = SRDCompendium._convert_cost(entry.get("cost"))
        desc_raw = entry.get("desc")
        description: str
        if isinstance(desc_raw, str):
            description = desc_raw.strip()
        elif isinstance(desc_raw, Iterable):
            parts = [str(part).strip() for part in desc_raw if str(part).strip()]
            description = "\n".join(parts)
        else:
            description = ""

        return EquipmentSummary(
            index=str(entry.get("index")),
            name=str(entry.get("name")),
            category=category,
            cost_gp=cost,
            weight=weight,
            description=description,
        )

    @staticmethod
    def _convert_cost(raw: object) -> Decimal | None:
        if not isinstance(raw, Mapping):
            return None
        quantity_raw = raw.get("quantity")
        unit_raw = raw.get("unit")
        try:
            quantity = Decimal(str(quantity_raw))
        except (TypeError, ValueError, ArithmeticError):
            return None
        if unit_raw is None:
            return None
        unit = str(unit_raw).strip().lower()
        conversion = {
            "cp": Decimal("0.01"),
            "sp": Decimal("0.1"),
            "ep": Decimal("0.5"),
            "gp": Decimal("1"),
            "pp": Decimal("10"),
        }.get(unit)
        if conversion is None:
            return None
        return (quantity * conversion).quantize(Decimal("0.01"))
