from decimal import Decimal

import pytest

from dndbank import DnDBank, EventCategory, QuestStatus
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
    quest = bank.add_quest("Investigate Ruins", summary="Ancient vault", reward="500 gp")
    note = bank.add_party_note("Patron", "Lady Winterhall offers support.", category="contact")
    resource = bank.add_resource("Group Inspiration", current=1, maximum=3, notes="Refreshes weekly")
    encounter = bank.create_encounter("Goblin Ambush", environment="Forest road", notes="Nighttime")
    bank.add_combatant(
        encounter.uid,
        name="Goblin Scout",
        initiative=15,
        armor_class=13,
        maximum_hp=7,
        current_hp=7,
        conditions=("Hidden",),
    )
    bank.set_active_encounter(encounter.uid)

    payload = bank.to_serialized()
    restored = DnDBank.from_serialized(payload)

    assert restored.list_characters() == ("Dorian",)
    restored_account = restored.get_character("Dorian")
    assert restored_account.balance == bank.get_character("Dorian").balance
    assert len(restored_account.transactions) == len(bank.get_character("Dorian").transactions)
    assert restored_account.sheet.character_class == "Sorcerer"
    assert restored_account.sheet.hit_points.maximum == 28
    assert restored_account.inventory[0].name == "Arcane Focus"
    restored_quest = restored.list_quests()[0]
    assert restored_quest.title == quest.title
    assert restored.list_party_notes()[0].title == note.title
    restored_resource = restored.list_resources()[0]
    assert restored_resource.name == resource.name
    restored_encounter = restored.list_encounters()[0]
    assert restored_encounter.name == encounter.name
    assert restored.get_active_encounter().uid == restored_encounter.uid
    assert restored_encounter.combatants[0].name == "Goblin Scout"


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


def test_quest_and_note_management():
    bank = DnDBank()

    quest = bank.add_quest("Rescue Mission", summary="Free the villagers", reward="Favor")
    assert quest.status is QuestStatus.ACTIVE

    updated = bank.update_quest(quest.uid, status=QuestStatus.COMPLETED)
    assert updated.status is QuestStatus.COMPLETED

    note = bank.add_party_note("Rumor", "A dragon nests nearby.", category="rumor")
    assert note.title == "Rumor"

    resource = bank.add_resource("Spell Slots", current=6, maximum=8)
    bank.adjust_resource(resource.uid, -2)
    refreshed = bank.update_resource(resource.uid, current=5, notes="After rest")
    assert refreshed.current == 5 and refreshed.notes == "After rest"

    bank.remove_quest(quest.uid)
    bank.remove_party_note(note.uid)
    bank.remove_resource(resource.uid)

    assert bank.list_quests() == ()
    assert bank.list_party_notes() == ()
    assert bank.list_resources() == ()


def test_combat_encounter_flow():
    bank = DnDBank()

    encounter = bank.create_encounter("Bandit Raid", environment="Village")
    bank.add_combatant(
        encounter.uid,
        name="Bandit Captain",
        initiative=18,
        armor_class=15,
        maximum_hp=65,
        current_hp=65,
        role="Boss",
    )
    bank.add_combatant(
        encounter.uid,
        name="Alina",
        initiative=16,
        armor_class=17,
        maximum_hp=42,
        current_hp=38,
        role="PC",
        player_character=True,
    )

    bank.advance_encounter(encounter.uid)
    bank.advance_encounter(encounter.uid)
    active = bank.get_encounter(encounter.uid)
    assert active.round == 2
    assert len(active.combatants) == 2

    bank.remove_combatant(encounter.uid, name="Bandit Captain")
    trimmed = bank.get_encounter(encounter.uid)
    assert len(trimmed.combatants) == 1
    assert trimmed.combatants[0].name == "Alina"

    bank.reset_encounter(encounter.uid)
    reset = bank.get_encounter(encounter.uid)
    assert reset.round == 1 and reset.active_index == 0
