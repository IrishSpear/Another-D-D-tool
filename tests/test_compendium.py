from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from dndbank.compendium import EquipmentSummary, SRDCompendium


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2))


def setup_compendium(tmp_path: Path) -> SRDCompendium:
    data_dir = tmp_path / "src" / "2014"
    data_dir.mkdir(parents=True)
    write_json(
        data_dir / "5e-SRD-Equipment.json",
        [
            {
                "index": "longsword",
                "name": "Longsword",
                "equipment_category": {"name": "Weapon"},
                "cost": {"quantity": 15, "unit": "gp"},
                "weight": 3,
                "desc": ["Versatile (1d10)", "Martial weapon"],
            },
            {
                "index": "torch",
                "name": "Torch",
                "equipment_category": {"name": "Adventuring Gear"},
                "cost": {"quantity": 1, "unit": "cp"},
                "weight": 1,
                "desc": ["Burns for one hour"],
            },
        ],
    )
    write_json(
        data_dir / "5e-SRD-Spells.json",
        [
            {"index": "fireball", "name": "Fireball", "level": 3},
            {"index": "shield", "name": "Shield", "level": 1},
        ],
    )
    return SRDCompendium(tmp_path)


def test_categories_reflect_available_files(tmp_path: Path) -> None:
    compendium = setup_compendium(tmp_path)
    assert "equipment" in compendium.categories
    assert "spells" in compendium.categories
    # Only the files we created should appear in the category list.
    assert set(compendium.categories).issuperset({"equipment", "spells"})


def test_get_equipment_returns_summary(tmp_path: Path) -> None:
    compendium = setup_compendium(tmp_path)
    summary = compendium.get_equipment("longsword")
    assert isinstance(summary, EquipmentSummary)
    assert summary.name == "Longsword"
    assert summary.category == "Weapon"
    assert summary.cost_gp == Decimal("15.00")
    assert "Versatile" in summary.description


def test_equipment_summary_to_inventory_item(tmp_path: Path) -> None:
    compendium = setup_compendium(tmp_path)
    summary = compendium.get_equipment("torch")
    item = summary.to_inventory_item(quantity=6, equipped=True)
    assert item.name == "Torch"
    assert item.quantity == 6
    assert item.category == "Adventuring Gear"
    assert item.value_gp == Decimal("0.01")
    assert item.equipped is True


def test_equipment_search_is_case_insensitive(tmp_path: Path) -> None:
    compendium = setup_compendium(tmp_path)
    matches = compendium.search_equipment("SWORD")
    assert [entry.index for entry in matches] == ["longsword"]


def test_generic_search_and_get(tmp_path: Path) -> None:
    compendium = setup_compendium(tmp_path)
    matches = compendium.search("spells", "shield")
    assert len(matches) == 1
    entry = compendium.get("spells", "fireball")
    assert entry["level"] == 3


def test_missing_repository_raises(tmp_path: Path) -> None:
    data_root = tmp_path / "not-present"
    with pytest.raises(FileNotFoundError):
        SRDCompendium(data_root)
