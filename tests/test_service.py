from decimal import Decimal

import pytest

from dndbank import DnDBank, EventCategory
from dndbank.exceptions import CharacterAlreadyExistsError, CharacterNotFoundError


def test_create_and_list_characters():
    bank = DnDBank()

    bank.create_character("Aelin", player="Sam", starting_gold=10)
    bank.create_character("Fen", starting_gold=0)

    assert bank.list_characters() == ("Aelin", "Fen")
    assert bank.get_character("Aelin").player == "Sam"


def test_duplicate_character_raises():
    bank = DnDBank()
    bank.create_character("Rowan")

    with pytest.raises(CharacterAlreadyExistsError):
        bank.create_character("Rowan")


def test_transfer_and_spend_flow():
    bank = DnDBank()
    bank.create_character("Lyra", starting_gold=15)
    bank.create_character("Iliad")

    bank.transfer_gold("Lyra", "Iliad", 5)
    bank.spend_gold("Iliad", 3, description="Supplies")

    assert bank.get_character("Lyra").balance == Decimal("10.00")
    assert bank.get_character("Iliad").balance == Decimal("2.00")


def test_distribute_loot_evenly():
    bank = DnDBank()
    bank.create_character("Morrigan")
    bank.create_character("Nesta")
    bank.create_character("Elain")

    txns = bank.distribute_loot(["Morrigan", "Nesta", "Elain"], total_amount=5)

    assert len(txns) == 3
    assert all(t.category is EventCategory.LOOT for t in txns)
    totals = [bank.get_character(name).balance for name in ("Morrigan", "Nesta", "Elain")]
    assert totals == [Decimal("1.67"), Decimal("1.67"), Decimal("1.66")]


def test_serialization_round_trip():
    bank = DnDBank()
    bank.create_character("Dorian", starting_gold=2)
    bank.earn_gold("Dorian", 3, description="Contract")
    bank.update_character_sheet(
        "Dorian",
        character_class="Sorcerer",
        level=4,
        notes="Silver-tongued diplomat",
    )
    bank.set_ability_scores("Dorian", charisma=18, wisdom=12)
    bank.set_hit_points("Dorian", maximum=28, current=18, temporary=4)
    bank.add_inventory_item("Dorian", item_name="Arcane Focus", category="Gear", equipped=True)

    payload = bank.to_serialized()
    restored = DnDBank.from_serialized(payload)

    assert restored.list_characters() == ("Dorian",)
    restored_account = restored.get_character("Dorian")
    assert restored_account.balance == bank.get_character("Dorian").balance
    assert len(restored_account.transactions) == len(bank.get_character("Dorian").transactions)
    assert restored_account.sheet.character_class == "Sorcerer"
    assert restored_account.sheet.hit_points.maximum == 28
    assert restored_account.inventory[0].name == "Arcane Focus"


def test_missing_character_raises_lookup_error():
    bank = DnDBank()

    with pytest.raises(CharacterNotFoundError):
        bank.get_character("Unknown")


def test_character_sheet_service_helpers():
    bank = DnDBank()
    bank.create_character("Kallias")

    updated = bank.update_character_sheet(
        "Kallias",
        ancestry="Dragonborn",
        character_class="Paladin",
        level=6,
    )
    assert updated.level == 6

    abilities = bank.set_ability_scores("Kallias", strength=18, charisma=14)
    assert abilities.strength == 18

    pool = bank.set_hit_points("Kallias", maximum=52, current=40)
    assert pool.maximum == 52

    after_damage = bank.adjust_hit_points("Kallias", -12)
    assert after_damage.current == 28


def test_inventory_service_flow():
    bank = DnDBank()
    bank.create_character("Seren")

    item = bank.add_inventory_item(
        "Seren",
        item_name="Longsword",
        quantity=1,
        category="Weapon",
        equipped=True,
    )
    assert item.equipped is True

    updated = bank.update_inventory_item(
        "Seren",
        "Longsword",
        description="Family heirloom",
        quantity=1,
    )
    assert "heirloom" in updated.description

    bank.remove_inventory_item("Seren", "Longsword")
    assert bank.list_inventory("Seren") == ()
