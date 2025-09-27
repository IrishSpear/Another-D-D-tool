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
