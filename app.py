"""Kidbank-inspired D&D treasury manager.

This module implements a small command line interface that can be used by a
Dungeon Master to track how much gold each adventurer currently has as well as
the reasons for every transaction.  The interface is intentionally minimalistic
so it can be run from any terminal during a session without additional
dependencies.

The underlying data is stored in a JSON file (``dnd_ledger.json`` by default).
Every command reads the file, applies the requested changes and then writes the
file back to disk.  This design keeps the application stateless and makes it
easy to place the JSON file under version control if desired.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_LEDGER_PATH = Path("dnd_ledger.json")


class LedgerError(RuntimeError):
    """Raised for predictable user facing errors."""


@dataclass
class Transaction:
    """Represents a single ledger movement."""

    timestamp: str
    character: str
    amount: int
    reason: str
    source: Optional[str] = None

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "timestamp": self.timestamp,
            "character": self.character,
            "amount": self.amount,
            "reason": self.reason,
            "source": self.source,
        }


@dataclass
class Character:
    """A D&D adventurer tracked by the ledger."""

    name: str
    player: Optional[str] = None
    balance: int = 0
    history: List[Transaction] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "player": self.player,
            "balance": self.balance,
            "history": [entry.as_dict() for entry in self.history],
        }


def _load_ledger(path: Path) -> Dict[str, Character]:
    if not path.exists():
        return {}

    data = json.loads(path.read_text())
    characters: Dict[str, Character] = {}
    for name, payload in data.items():
        characters[name] = Character(
            name=payload["name"],
            player=payload.get("player"),
            balance=payload.get("balance", 0),
            history=[
                Transaction(
                    timestamp=entry["timestamp"],
                    character=entry["character"],
                    amount=int(entry["amount"]),
                    reason=entry.get("reason", ""),
                    source=entry.get("source"),
                )
                for entry in payload.get("history", [])
            ],
        )

    return characters


def _save_ledger(path: Path, characters: Dict[str, Character]) -> None:
    data = {name: char.as_dict() for name, char in characters.items()}
    path.write_text(json.dumps(data, indent=2))


def _get_or_create(characters: Dict[str, Character], name: str) -> Character:
    if name not in characters:
        raise LedgerError(f"Character '{name}' does not exist. Use 'create' first.")
    return characters[name]


def _ensure_new(characters: Dict[str, Character], name: str) -> None:
    if name in characters:
        raise LedgerError(f"Character '{name}' already exists.")


def _timestamp() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def create_character(args: argparse.Namespace) -> None:
    characters = _load_ledger(args.ledger)
    _ensure_new(characters, args.name)
    characters[args.name] = Character(name=args.name, player=args.player)
    _save_ledger(args.ledger, characters)
    print(f"Created character '{args.name}'")


def earn_gold(args: argparse.Namespace) -> None:
    characters = _load_ledger(args.ledger)
    character = _get_or_create(characters, args.name)
    amount = int(args.amount)
    character.balance += amount
    character.history.append(
        Transaction(
            timestamp=_timestamp(),
            character=character.name,
            amount=amount,
            reason=args.reason or "Treasure",
            source="earn",
        )
    )
    _save_ledger(args.ledger, characters)
    print(f"Added {amount} gp to {character.name}. New balance: {character.balance} gp")


def spend_gold(args: argparse.Namespace) -> None:
    characters = _load_ledger(args.ledger)
    character = _get_or_create(characters, args.name)
    amount = int(args.amount)
    if amount > character.balance:
        raise LedgerError(
            f"Cannot spend {amount} gp; {character.name} only has {character.balance} gp"
        )
    character.balance -= amount
    character.history.append(
        Transaction(
            timestamp=_timestamp(),
            character=character.name,
            amount=-amount,
            reason=args.reason or "Purchase",
            source="spend",
        )
    )
    _save_ledger(args.ledger, characters)
    print(
        f"Spent {amount} gp from {character.name}. New balance: {character.balance} gp"
    )


def transfer_gold(args: argparse.Namespace) -> None:
    characters = _load_ledger(args.ledger)
    source = _get_or_create(characters, args.source)
    target = _get_or_create(characters, args.target)
    amount = int(args.amount)
    if amount > source.balance:
        raise LedgerError(
            f"Cannot transfer {amount} gp; {source.name} only has {source.balance} gp"
        )

    source.balance -= amount
    target.balance += amount

    timestamp = _timestamp()
    reason = args.reason or f"Transfer to {target.name}"
    source.history.append(
        Transaction(
            timestamp=timestamp,
            character=source.name,
            amount=-amount,
            reason=reason,
            source="transfer",
        )
    )
    target.history.append(
        Transaction(
            timestamp=timestamp,
            character=target.name,
            amount=amount,
            reason=args.reason or f"Transfer from {source.name}",
            source="transfer",
        )
    )

    _save_ledger(args.ledger, characters)
    print(
        f"Transferred {amount} gp from {source.name} to {target.name}."
        f" Balances: {source.name}={source.balance} gp, {target.name}={target.balance} gp"
    )


def show_status(args: argparse.Namespace) -> None:
    characters = _load_ledger(args.ledger)
    if args.name:
        character = _get_or_create(characters, args.name)
        print(_format_character_summary(character))
        return

    if not characters:
        print("No characters in ledger. Use 'create' to add one.")
        return

    for character in sorted(characters.values(), key=lambda c: c.name.lower()):
        print(_format_character_summary(character))
        print("-" * 40)


def show_history(args: argparse.Namespace) -> None:
    characters = _load_ledger(args.ledger)
    character = _get_or_create(characters, args.name)
    if not character.history:
        print(f"No transactions recorded for {character.name}.")
        return

    for entry in character.history:
        direction = "received" if entry.amount >= 0 else "spent"
        amount = abs(entry.amount)
        print(
            f"[{entry.timestamp}] {character.name} {direction} {amount} gp"
            f" for {entry.reason} (via {entry.source})"
        )


def _format_character_summary(character: Character) -> str:
    player_info = f" (Player: {character.player})" if character.player else ""
    return f"{character.name}{player_info}: {character.balance} gp"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage an adventuring party's gold with a simple ledger."
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help="Path to the JSON ledger file. Defaults to ./dnd_ledger.json",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a new character")
    create.add_argument("name", help="Character name")
    create.add_argument("--player", help="Player owning the character")
    create.set_defaults(func=create_character)

    earn = subparsers.add_parser("earn", help="Record that a character found gold")
    earn.add_argument("name", help="Character name")
    earn.add_argument("amount", help="Amount of gold pieces earned", type=int)
    earn.add_argument("--reason", help="Why the gold was earned")
    earn.set_defaults(func=earn_gold)

    spend = subparsers.add_parser("spend", help="Record that a character spent gold")
    spend.add_argument("name", help="Character name")
    spend.add_argument("amount", help="Amount of gold pieces spent", type=int)
    spend.add_argument("--reason", help="What the gold was spent on")
    spend.set_defaults(func=spend_gold)

    transfer = subparsers.add_parser("transfer", help="Move gold between characters")
    transfer.add_argument("source", help="Character sending the gold")
    transfer.add_argument("target", help="Character receiving the gold")
    transfer.add_argument("amount", help="Amount of gold pieces", type=int)
    transfer.add_argument("--reason", help="Reason for the transfer")
    transfer.set_defaults(func=transfer_gold)

    status = subparsers.add_parser(
        "status", help="Show balances for all characters or a single one"
    )
    status.add_argument("name", nargs="?", help="Character name")
    status.set_defaults(func=show_status)

    history = subparsers.add_parser(
        "history", help="Display a character's transaction history"
    )
    history.add_argument("name", help="Character name")
    history.set_defaults(func=show_history)

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except LedgerError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()

