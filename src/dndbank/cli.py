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
from .models import CharacterSheet, EventCategory, InventoryItem, TransactionType
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


def parse_assignments(values: Iterable[str]) -> dict[str, int]:
    assignments: dict[str, int] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"Expected KEY=VALUE format for '{raw}'.")
        key, value = raw.split("=", 1)
        cleaned_key = key.strip().lower()
        cleaned_value = value.strip()
        if not cleaned_key or not cleaned_value:
            raise ValueError(f"Invalid assignment '{raw}'.")
        assignments[cleaned_key] = int(cleaned_value)
    return assignments


def render_sheet(name: str, sheet: CharacterSheet) -> None:
    print(f"{name}'s character sheet")
    header: list[str] = []
    if sheet.character_class:
        header.append(sheet.character_class)
    if sheet.ancestry:
        header.append(sheet.ancestry)
    if sheet.background:
        header.append(f"Background: {sheet.background}")
    if sheet.alignment:
        header.append(f"Alignment: {sheet.alignment}")
    if header:
        print(" • ".join(header))
    print(f"Level {sheet.level} — {sheet.experience} XP — Proficiency +{sheet.proficiency_bonus}")
    hp = sheet.hit_points
    hp_line = f"HP {hp.current}/{hp.maximum} (+{hp.temporary} temp)"
    if sheet.inspiration:
        hp_line += " — Inspiration"
    print(hp_line)
    if sheet.passive_perception is not None:
        print(f"Passive Perception: {sheet.passive_perception}")
    ability_parts: list[str] = []
    for ability, score in sheet.ability_scores.as_dict().items():
        mod = sheet.ability_scores.modifier(ability)
        ability_parts.append(f"{ability[:3].title()} {score} ({mod:+d})")
    print("Abilities: " + ", ".join(ability_parts))
    if sheet.notes:
        print(f"Notes: {sheet.notes}")


def format_inventory_item(item: InventoryItem) -> str:
    parts = [f"{item.name} x{item.quantity}"]
    if item.category:
        parts.append(f"[{item.category}]")
    if item.equipped:
        parts.append("(equipped)")
    if item.weight is not None:
        parts.append(f"{item.weight} lb")
    if item.value_gp is not None:
        parts.append(format_gp(item.value_gp))
    if item.description:
        parts.append(f"— {item.description}")
    return " ".join(parts)


def cmd_sheet(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        bank.get_character(args.name)
    except CharacterNotFoundError as exc:
        raise SystemExit(str(exc))

    updates: dict[str, object] = {}
    if args.character_class:
        updates["character_class"] = args.character_class
    if args.ancestry:
        updates["ancestry"] = args.ancestry
    if args.background:
        updates["background"] = args.background
    if args.alignment:
        updates["alignment"] = args.alignment
    if args.level is not None:
        updates["level"] = args.level
    if args.experience is not None:
        updates["experience"] = args.experience
    if args.proficiency is not None:
        updates["proficiency_bonus"] = args.proficiency
    if args.passive_perception is not None:
        updates["passive_perception"] = args.passive_perception
    if args.notes is not None:
        updates["notes"] = args.notes
    if args.inspiration is not None:
        updates["inspiration"] = args.inspiration

    ability_updates: dict[str, int] = {}
    hp_updates: dict[str, int] = {}
    if args.ability:
        try:
            ability_updates = parse_assignments(args.ability)
        except ValueError as exc:
            raise SystemExit(str(exc))
        alias_map = {
            "str": "strength",
            "dex": "dexterity",
            "con": "constitution",
            "int": "intelligence",
            "wis": "wisdom",
            "cha": "charisma",
        }
        ability_updates = {
            alias_map.get(key, key): value for key, value in ability_updates.items()
        }
    if args.hit_points:
        try:
            hp_updates = parse_assignments(args.hit_points)
        except ValueError as exc:
            raise SystemExit(str(exc))

    if updates:
        bank.update_character_sheet(args.name, **updates)
    if ability_updates:
        bank.set_ability_scores(args.name, **ability_updates)
    if hp_updates:
        bank.set_hit_points(
            args.name,
            maximum=hp_updates.get("maximum"),
            current=hp_updates.get("current"),
            temporary=hp_updates.get("temporary"),
        )

    if updates or ability_updates or hp_updates:
        save_bank(args.ledger, bank)
        print(f"Updated sheet for {args.name}.")

    render_sheet(args.name, bank.get_character_sheet(args.name))


def cmd_inventory_list(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        items = bank.list_inventory(args.name)
    except CharacterNotFoundError as exc:
        raise SystemExit(str(exc))

    if not items:
        print(f"{args.name} carries nothing.")
        return

    for item in items:
        print(format_inventory_item(item))


def cmd_inventory_add(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        item = bank.add_inventory_item(
            args.name,
            item_name=args.item,
            quantity=args.quantity,
            description=args.description,
            weight=args.weight,
            value_gp=args.value,
            category=args.category,
            equipped=args.equipped,
        )
    except (CharacterNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc))
    save_bank(args.ledger, bank)
    print(f"Added {item.name} x{item.quantity} to {args.name}.")


def cmd_inventory_update(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        item = bank.update_inventory_item(
            args.name,
            args.item,
            quantity=args.quantity,
            description=args.description,
            weight=args.weight,
            value_gp=args.value,
            category=args.category,
            equipped=args.equipped,
        )
    except (CharacterNotFoundError, KeyError, ValueError) as exc:
        raise SystemExit(str(exc))
    save_bank(args.ledger, bank)
    print(f"Updated {item.name} for {args.name} (now x{item.quantity}).")


def cmd_inventory_remove(args: argparse.Namespace) -> None:
    bank = load_bank(args.ledger)
    try:
        bank.remove_inventory_item(args.name, args.item, quantity=args.quantity)
    except (CharacterNotFoundError, KeyError, ValueError) as exc:
        raise SystemExit(str(exc))
    save_bank(args.ledger, bank)
    if args.quantity is None:
        print(f"Removed {args.item} from {args.name}.")
    else:
        print(f"Removed {args.quantity} of {args.item} from {args.name}.")


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

    sheet = subparsers.add_parser("sheet", help="View or update a character sheet")
    sheet.add_argument("name")
    sheet.add_argument("--class", dest="character_class")
    sheet.add_argument("--ancestry")
    sheet.add_argument("--background")
    sheet.add_argument("--alignment")
    sheet.add_argument("--level", type=int)
    sheet.add_argument("--experience", type=int)
    sheet.add_argument("--proficiency", type=int)
    sheet.add_argument("--passive-perception", dest="passive_perception", type=int)
    sheet.add_argument("--notes")
    sheet.add_argument("--inspiration", dest="inspiration", action="store_true")
    sheet.add_argument("--no-inspiration", dest="inspiration", action="store_false")
    sheet.add_argument(
        "--ability",
        action="append",
        metavar="ABILITY=VALUE",
        help="Override an ability score (repeatable)",
    )
    sheet.add_argument(
        "--hit-points",
        dest="hit_points",
        action="append",
        metavar="FIELD=VALUE",
        help="Adjust hit point pool (current, maximum, temporary)",
    )
    sheet.set_defaults(inspiration=None, func=cmd_sheet)

    inventory = subparsers.add_parser("inventory", help="Manage a character's inventory")
    inv_subparsers = inventory.add_subparsers(dest="inventory_command", required=True)

    inv_list = inv_subparsers.add_parser("list", help="Display carried items")
    inv_list.add_argument("name")
    inv_list.set_defaults(func=cmd_inventory_list)

    inv_add = inv_subparsers.add_parser("add", help="Add or increase an item")
    inv_add.add_argument("name")
    inv_add.add_argument("item")
    inv_add.add_argument("--quantity", type=int, default=1)
    inv_add.add_argument("--description")
    inv_add.add_argument("--weight", type=float)
    inv_add.add_argument("--value")
    inv_add.add_argument("--category")
    inv_add.add_argument("--equipped", action="store_true")
    inv_add.set_defaults(func=cmd_inventory_add)

    inv_update = inv_subparsers.add_parser("update", help="Edit an existing item")
    inv_update.add_argument("name")
    inv_update.add_argument("item")
    inv_update.add_argument("--quantity", type=int)
    inv_update.add_argument("--description")
    inv_update.add_argument("--weight", type=float)
    inv_update.add_argument("--value")
    inv_update.add_argument("--category")
    inv_update.add_argument("--equipped", action="store_true")
    inv_update.add_argument("--unequipped", dest="equipped", action="store_false")
    inv_update.set_defaults(equipped=None, func=cmd_inventory_update)

    inv_remove = inv_subparsers.add_parser("remove", help="Remove an item or reduce quantity")
    inv_remove.add_argument("name")
    inv_remove.add_argument("item")
    inv_remove.add_argument("--quantity", type=int)
    inv_remove.set_defaults(func=cmd_inventory_remove)

    return parser


def main(argv: Iterable[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()
