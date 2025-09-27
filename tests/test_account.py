from decimal import Decimal

import pytest

from dndbank.account import CharacterAccount
from dndbank.exceptions import InsufficientFundsError
from dndbank.models import EventCategory, TransactionType


def test_starting_balance_records_adjustment_transaction():
    account = CharacterAccount("Mira", starting_gold=5)

    assert account.balance == Decimal("5.00")
    assert len(account.transactions) == 1
    initial = account.transactions[0]
    assert initial.type is TransactionType.ADJUSTMENT
    assert initial.amount == Decimal("5.00")


def test_earn_adds_to_balance_and_history():
    account = CharacterAccount("Talen")

    txn = account.earn(10, "Quest reward", category=EventCategory.QUEST)

    assert account.balance == Decimal("10.00")
    assert txn in account.transactions
    assert txn.category is EventCategory.QUEST
    assert txn.type is TransactionType.EARN


def test_spend_requires_sufficient_balance():
    account = CharacterAccount("Nyx", starting_gold=3)

    with pytest.raises(InsufficientFundsError):
        account.spend(10)

    spent = account.spend(2, "Potion")
    assert account.balance == Decimal("1.00")
    assert spent.type is TransactionType.SPEND


def test_transfer_between_accounts():
    source = CharacterAccount("Thorn", starting_gold=12)
    target = CharacterAccount("Elira")

    outgoing, incoming = source.transfer_to(target, 5, description="Shared expenses")

    assert source.balance == Decimal("7.00")
    assert target.balance == Decimal("5.00")
    assert outgoing.type is TransactionType.TRANSFER_OUT
    assert incoming.type is TransactionType.TRANSFER_IN


def test_character_sheet_and_hit_points():
    account = CharacterAccount("Rook")

    sheet = account.update_sheet(
        character_class="Wizard",
        ancestry="Elf",
        level=5,
        experience=6500,
        notes="Member of the Sapphire Cabal",
    )
    assert sheet.character_class == "Wizard"
    assert sheet.level == 5
    assert sheet.experience == 6500

    abilities = account.set_ability_scores(strength=8, dexterity=16, intelligence=18)
    assert abilities.dexterity == 16
    assert abilities.modifier("intelligence") == 4

    pool = account.set_hit_points(maximum=35, current=22, temporary=5)
    assert pool.maximum == 35
    assert pool.current == 22
    assert pool.temporary == 5

    new_pool = account.adjust_hit_points(-10)
    assert new_pool.current == 17  # 5 temp absorbed, 5 damage applied


def test_inventory_management():
    account = CharacterAccount("Lyric")

    potion = account.add_inventory_item(
        "Healing Potion",
        quantity=2,
        description="Restores 2d4+2 HP",
        value_gp="50",
        category="Consumable",
    )
    assert potion.quantity == 2

    stacked = account.add_inventory_item("Healing Potion", quantity=1)
    assert stacked.quantity == 3

    updated = account.update_inventory_item(
        "Healing Potion",
        quantity=5,
        equipped=False,
        description="Standard healing potion",
    )
    assert updated.quantity == 5
    assert "Standard" in updated.description

    account.remove_inventory_item("Healing Potion", quantity=2)
    assert account.list_inventory()[0].quantity == 3

    account.remove_inventory_item("Healing Potion")
    assert account.list_inventory() == ()

    with pytest.raises(KeyError):
        account.remove_inventory_item("Unknown Item")
