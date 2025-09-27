"""Command line interface mirroring the KidBank tooling layout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from .exceptions import (
    CharacterAlreadyExistsError,
    CharacterNotFoundError,
    InsufficientFundsError,
)
from .models import EventCategory, TransactionType
from .money import format_gp
from .service import DnDBank

DEFAULT_LEDGER = Path("dnd_ledger.json")


def load_bank(path: Path) -> DnDBank:
    if not path.exists():
        return DnDBank()
    data = json.loads(path.read_text())
    return DnDBank.from_serialized(data)


def save_bank(path: Path, bank: DnDBank) -> None:
    path.write_text(json.dumps(bank.to_serialized(), indent=2))


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER,
        help="Path to the persistent ledger file (default: ./dnd_ledger.json)",
    )


def cmd_create(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        bank.create_character(args.name, player=args.player, starting_gold=args.gold)
    except CharacterAlreadyExistsError as exc:
        raise SystemExit(str(exc))
    save_bank(args.ledger, bank)
    print(f"Created {args.name} with starting balance {format_gp(args.gold)}")


def cmd_earn(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        txn = bank.earn_gold(
            args.name,
            args.amount,
            description=args.reason,
            category=EventCategory(args.category) if args.category else None,
        )
    except (CharacterNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc))
    save_bank(args.ledger, bank)
    print(
        f"{args.name} earned {format_gp(txn.amount)} for {txn.description}. "
        f"New balance: {format_gp(bank.get_character(args.name).balance)}"
    )


def cmd_spend(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        txn = bank.spend_gold(
            args.name,
            args.amount,
            description=args.reason,
            category=EventCategory(args.category) if args.category else None,
        )
    except (CharacterNotFoundError, ValueError, InsufficientFundsError) as exc:
        raise SystemExit(str(exc))
    save_bank(args.ledger, bank)
    print(
        f"{args.name} spent {format_gp(txn.amount)} on {txn.description}. "
        f"New balance: {format_gp(bank.get_character(args.name).balance)}"
    )


def cmd_transfer(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        outgoing, incoming = bank.transfer_gold(
            args.source,
            args.target,
            args.amount,
            description=args.reason,
        )
    except (CharacterNotFoundError, ValueError, InsufficientFundsError) as exc:
        raise SystemExit(str(exc))
    save_bank(args.ledger, bank)
    source_balance = bank.get_character(args.source).balance
    target_balance = bank.get_character(args.target).balance
    print(
        f"Transferred {format_gp(outgoing.amount)} from {args.source} to {args.target}. "
        f"Balances: {format_gp(source_balance)} / {format_gp(target_balance)}"
    )


def cmd_status(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    if args.name:
        try:
            account = bank.get_character(args.name)
        except CharacterNotFoundError as exc:
            raise SystemExit(str(exc))
        print(account.summary())
        return

    if not bank.list_characters():
        print("No characters recorded. Use 'create' to add one.")
        return

    for name in bank.list_characters():
        account = bank.get_character(name)
        print(account.summary())


def cmd_history(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        account = bank.get_character(args.name)
    except CharacterNotFoundError as exc:
        raise SystemExit(str(exc))

    if not account.transactions:
        print(f"No transactions recorded for {args.name}.")
        return

    for entry in account.transactions:
        verb = {
            TransactionType.EARN: "received",
            TransactionType.TRANSFER_IN: "received",
            TransactionType.SPEND: "spent",
            TransactionType.TRANSFER_OUT: "transferred",
            TransactionType.ADJUSTMENT: "adjusted",
        }[entry.type]
        amount = format_gp(entry.amount)
        print(
            f"[{entry.timestamp.isoformat()}] {args.name} {verb} {amount}"
            f" for {entry.description} ({entry.category.value})"
        )


def cmd_distribute(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        txns = bank.distribute_loot(
            args.characters,
            total_amount=args.amount,
            description=args.reason,
            category=EventCategory(args.category) if args.category else EventCategory.LOOT,
        )
    except (CharacterNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc))
    save_bank(args.ledger, bank)
    amount = format_gp(args.amount)
    names = ", ".join(args.characters)
    print(f"Split {amount} across {names} ({len(txns)} shares recorded)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage D&D treasure with a KidBank-style toolkit.",
    )
    add_common_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Register a new adventurer")
    create.add_argument("name")
    create.add_argument("--player", help="Player owning the character")
    create.add_argument("--gold", type=float, default=0, help="Starting gold pieces")
    create.set_defaults(func=cmd_create)

    earn = subparsers.add_parser("earn", help="Record loot for an adventurer")
    earn.add_argument("name")
    earn.add_argument("amount", type=float)
    earn.add_argument("--reason", default="Treasure haul")
    earn.add_argument(
        "--category",
        choices=[c.value for c in EventCategory],
        help="Optional event category",
    )
    earn.set_defaults(func=cmd_earn)

    spend = subparsers.add_parser("spend", help="Log purchases or expenses")
    spend.add_argument("name")
    spend.add_argument("amount", type=float)
    spend.add_argument("--reason", default="Purchase")
    spend.add_argument(
        "--category",
        choices=[c.value for c in EventCategory],
        help="Optional event category",
    )
    spend.set_defaults(func=cmd_spend)

    transfer = subparsers.add_parser("transfer", help="Move gold between characters")
    transfer.add_argument("source")
    transfer.add_argument("target")
    transfer.add_argument("amount", type=float)
    transfer.add_argument("--reason", help="Narrative for the transfer")
    transfer.set_defaults(func=cmd_transfer)

    status = subparsers.add_parser("status", help="View balances")
    status.add_argument("name", nargs="?")
    status.set_defaults(func=cmd_status)

    history = subparsers.add_parser("history", help="Inspect a ledger history")
    history.add_argument("name")
    history.set_defaults(func=cmd_history)

    distribute = subparsers.add_parser(
        "distribute",
        help="Evenly distribute loot across a list of characters",
    )
    distribute.add_argument("amount", type=float)
    distribute.add_argument("characters", nargs="+", help="Characters sharing the loot")
    distribute.add_argument("--reason", default="Split loot")
    distribute.add_argument(
        "--category",
        choices=[c.value for c in EventCategory],
        help="Optional event category",
    )
    distribute.set_defaults(func=cmd_distribute)

    return parser


def main(argv: Iterable[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()
