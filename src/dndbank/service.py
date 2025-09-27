"""High-level facade for orchestrating character accounts."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from typing import Iterable, Mapping, Optional, Tuple

from .account import CharacterAccount
from .exceptions import CharacterAlreadyExistsError, CharacterNotFoundError
from .models import EventCategory, Transaction
from .money import AmountLike, to_decimal


class DnDBank:
    """Manage a party's collection of ``CharacterAccount`` objects."""

    __slots__ = ("_accounts",)

    @classmethod
    def from_serialized(cls, payload: Mapping[str, object]) -> "DnDBank":
        bank = cls()
        for raw in payload.get("characters", []):
            account = CharacterAccount.from_serialized(raw)
            bank._accounts[account.name] = account
        return bank

    def __init__(self) -> None:
        self._accounts: dict[str, CharacterAccount] = {}

    def list_characters(self) -> Tuple[str, ...]:
        """Return character names in alphabetical order."""

        return tuple(sorted(self._accounts))

    def create_character(
        self,
        name: str,
        *,
        player: str | None = None,
        starting_gold: AmountLike = 0,
    ) -> CharacterAccount:
        if name in self._accounts:
            raise CharacterAlreadyExistsError(f"Character '{name}' already exists.")
        account = CharacterAccount(name, player=player, starting_gold=starting_gold)
        self._accounts[name] = account
        return account

    def get_character(self, name: str) -> CharacterAccount:
        try:
            return self._accounts[name]
        except KeyError as exc:
            raise CharacterNotFoundError(name) from exc

    def earn_gold(
        self,
        name: str,
        amount: AmountLike,
        description: str = "Treasure haul",
        *,
        category: EventCategory | None = None,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> Transaction:
        character = self.get_character(name)
        return character.earn(amount, description, category=category, metadata=metadata)

    def spend_gold(
        self,
        name: str,
        amount: AmountLike,
        description: str = "Purchase",
        *,
        category: EventCategory | None = None,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> Transaction:
        character = self.get_character(name)
        return character.spend(amount, description, category=category, metadata=metadata)

    def transfer_gold(
        self,
        source: str,
        target: str,
        amount: AmountLike,
        description: str | None = None,
        *,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> tuple[Transaction, Transaction]:
        source_account = self.get_character(source)
        target_account = self.get_character(target)
        if source_account is target_account:
            raise ValueError("Cannot transfer to the same character.")
        return source_account.transfer_to(
            target_account,
            amount,
            description,
            metadata=metadata,
        )

    def distribute_loot(
        self,
        names: Iterable[str],
        *,
        total_amount: AmountLike,
        description: str = "Split loot",
        category: EventCategory = EventCategory.LOOT,
    ) -> tuple[Transaction, ...]:
        accounts = [self.get_character(name) for name in names]
        if not accounts:
            return tuple()

        total_value = to_decimal(total_amount)
        share = (total_value / len(accounts)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        remainder = total_value - (share * len(accounts))

        transactions: list[Transaction] = []
        for account in accounts:
            top_up = Decimal("0")
            if remainder > Decimal("0"):
                top_up = Decimal("0.01")
                remainder -= top_up
            transactions.append(
                account.earn(
                    share + top_up,
                    description,
                    category=category,
                    metadata={"distribution": "loot"},
                )
            )
        return tuple(transactions)

    def to_serialized(self) -> dict[str, object]:
        return {
            "characters": [
                self._accounts[name].to_serialized() for name in self.list_characters()
            ]
        }
