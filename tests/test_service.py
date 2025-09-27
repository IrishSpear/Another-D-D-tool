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

    payload = bank.to_serialized()
    restored = DnDBank.from_serialized(payload)

    assert restored.list_characters() == ("Dorian",)
    restored_account = restored.get_character("Dorian")
    assert restored_account.balance == bank.get_character("Dorian").balance
    assert len(restored_account.transactions) == len(bank.get_character("Dorian").transactions)


def test_missing_character_raises_lookup_error():
    bank = DnDBank()

    with pytest.raises(CharacterNotFoundError):
        bank.get_character("Unknown")
