"""Flask-powered web interface that mirrors the KidBank experience."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterable

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from .exceptions import (
    CharacterAlreadyExistsError,
    CharacterNotFoundError,
    InsufficientFundsError,
)
from .models import EventCategory
from .money import format_gp
from .service import DnDBank


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the KidBank-style D&D ledger web app."""

    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("DND_BANK_SECRET_KEY", "dev"),
        LEDGER_PATH="dnd_ledger.json",
    )
    if config:
        app.config.update(config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    def ledger_path() -> Path:
        raw_path = app.config["LEDGER_PATH"]
        path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
        if not path.is_absolute():
            path = Path(app.instance_path) / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def load_bank() -> DnDBank:
        path = ledger_path()
        if not path.exists():
            return DnDBank()
        data = json.loads(path.read_text())
        return DnDBank.from_serialized(data)

    def save_bank(bank: DnDBank) -> None:
        path = ledger_path()
        path.write_text(json.dumps(bank.to_serialized(), indent=2))

    def post_action(fn: Callable[[DnDBank], None]) -> Callable[[], Any]:
        @wraps(fn)
        def wrapper() -> Any:
            bank = load_bank()
            try:
                fn(bank)
            except ValueError as exc:
                flash(str(exc), "error")
            except CharacterAlreadyExistsError as exc:
                flash(str(exc), "error")
            except (CharacterNotFoundError, InsufficientFundsError) as exc:
                flash(str(exc), "error")
            else:
                save_bank(bank)
            return redirect(url_for("dashboard"))

        return wrapper

    @app.template_filter("format_gp")
    def format_gp_filter(value: object) -> str:
        return format_gp(value)

    @app.context_processor
    def inject_categories() -> dict[str, Iterable[EventCategory]]:
        return {"categories": list(EventCategory)}

    @app.route("/")
    def dashboard() -> str:
        bank = load_bank()
        characters = []
        total = Decimal("0")
        for name in bank.list_characters():
            account = bank.get_character(name)
            total += account.balance
            history = list(account.transactions)
            characters.append(
                {
                    "name": account.name,
                    "player": account.player,
                    "balance": account.balance,
                    "recent": history[-5:][::-1],
                }
            )
        return render_template(
            "dashboard.html",
            characters=characters,
            total_balance=total,
        )

    @app.post("/characters")
    @post_action
    def create_character(bank: DnDBank) -> None:
        name = request.form.get("name", "").strip()
        player = request.form.get("player", "").strip() or None
        gold = request.form.get("starting_gold", "0").strip() or "0"
        if not name:
            raise ValueError("Character name is required.")
        bank.create_character(name, player=player, starting_gold=gold)
        flash(f"Created {name}.", "success")

    @app.post("/earn")
    @post_action
    def earn_gold(bank: DnDBank) -> None:
        name = request.form.get("name", "").strip()
        amount = request.form.get("amount", "0").strip() or "0"
        reason = request.form.get("reason", "Treasure haul")
        category_raw = request.form.get("category")
        category = EventCategory(category_raw) if category_raw else None
        if not name:
            raise ValueError("Select a character to award loot to.")
        txn = bank.earn_gold(name, amount, description=reason, category=category)
        flash(
            f"{name} gained {format_gp(txn.amount)} for {txn.description}.",
            "success",
        )

    @app.post("/spend")
    @post_action
    def spend_gold(bank: DnDBank) -> None:
        name = request.form.get("name", "").strip()
        amount = request.form.get("amount", "0").strip() or "0"
        reason = request.form.get("reason", "Purchase")
        category_raw = request.form.get("category")
        category = EventCategory(category_raw) if category_raw else None
        if not name:
            raise ValueError("Select a character to spend from.")
        txn = bank.spend_gold(name, amount, description=reason, category=category)
        flash(
            f"{name} spent {format_gp(txn.amount)} on {txn.description}.",
            "success",
        )

    @app.post("/transfer")
    @post_action
    def transfer_gold(bank: DnDBank) -> None:
        source = request.form.get("source", "").strip()
        target = request.form.get("target", "").strip()
        amount = request.form.get("amount", "0").strip() or "0"
        reason = request.form.get("reason") or None
        if not source or not target:
            raise ValueError("Select both source and target characters.")
        bank.transfer_gold(source, target, amount, description=reason)
        flash(
            f"Transferred {format_gp(amount)} from {source} to {target}.",
            "success",
        )

    @app.post("/distribute")
    @post_action
    def distribute_loot(bank: DnDBank) -> None:
        names = request.form.getlist("characters")
        amount = request.form.get("amount", "0").strip() or "0"
        reason = request.form.get("reason", "Split loot")
        category_raw = request.form.get("category")
        category = EventCategory(category_raw) if category_raw else EventCategory.LOOT
        if not names:
            raise ValueError("Select at least one adventurer to split loot amongst.")
        bank.distribute_loot(
            names,
            total_amount=amount,
            description=reason,
            category=category,
        )
        flash(
            f"Split {format_gp(amount)} across {', '.join(names)}.",
            "success",
        )

    return app


def main() -> None:
    app = create_app()
    app.run(debug=True)


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    main()
