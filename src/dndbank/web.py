"""FastAPI-powered web interface that mirrors the KidBank experience."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Annotated
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .exceptions import (
    CharacterAlreadyExistsError,
    CharacterNotFoundError,
    InsufficientFundsError,
)
from .models import EventCategory
from .money import format_gp
from .service import DnDBank


def create_app(config: dict[str, Any] | None = None) -> FastAPI:
    """Create and configure the KidBank-style D&D ledger web app."""

    package_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(package_dir / "templates"))
    templates.env.filters["format_gp"] = format_gp

    app = FastAPI(title="D&D Bank", version="0.1.0")

    cfg: dict[str, Any] = {"LEDGER_PATH": Path("instance/dnd_ledger.json")}
    if config:
        cfg.update(config)

    raw_ledger_path = cfg["LEDGER_PATH"]
    ledger_path = raw_ledger_path if isinstance(raw_ledger_path, Path) else Path(raw_ledger_path)
    if not ledger_path.is_absolute():
        ledger_path = Path.cwd() / ledger_path
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    app.mount("/static", StaticFiles(directory=str(package_dir / "static")), name="static")

    def load_bank() -> DnDBank:
        if not ledger_path.exists():
            return DnDBank()
        data = json.loads(ledger_path.read_text())
        return DnDBank.from_serialized(data)

    def save_bank(bank: DnDBank) -> None:
        payload = json.dumps(bank.to_serialized(), indent=2)
        ledger_path.write_text(payload)

    def to_messages(request: Request) -> list[dict[str, str]]:
        texts = request.query_params.getlist("message")
        categories = request.query_params.getlist("category")
        messages = []
        for index, text in enumerate(texts):
            category = categories[index] if index < len(categories) else "info"
            messages.append({"category": category, "text": text})
        return messages

    def redirect_with_message(request: Request, message: str, category: str) -> RedirectResponse:
        target = request.url_for("dashboard")
        query = urlencode([("message", message), ("category", category)])
        return RedirectResponse(url=f"{target}?{query}", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        bank = load_bank()
        characters: list[dict[str, object]] = []
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
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "request": request,
                "characters": characters,
                "total_balance": total,
                "messages": to_messages(request),
                "categories": list(EventCategory),
            },
        )

    @app.post("/characters")
    async def create_character(
        request: Request,
        name: Annotated[str, Form(...)],
        player: Annotated[str | None, Form()] = None,
        starting_gold: Annotated[str, Form()] = "0",
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_name = name.strip()
        cleaned_player = (player or "").strip() or None
        starting = (starting_gold or "0").strip() or "0"
        if not cleaned_name:
            return redirect_with_message(request, "Character name is required.", "error")
        try:
            bank.create_character(cleaned_name, player=cleaned_player, starting_gold=starting)
        except CharacterAlreadyExistsError as exc:
            return redirect_with_message(request, str(exc), "error")
        except ValueError as exc:
            return redirect_with_message(request, str(exc), "error")
        else:
            save_bank(bank)
            return redirect_with_message(request, f"Created {cleaned_name}.", "success")

    def parse_category(raw: str | None) -> EventCategory | None:
        value = (raw or "").strip()
        if not value:
            return None
        try:
            return EventCategory(value)
        except ValueError as exc:
            raise ValueError(f"Unknown category '{value}'.") from exc

    @app.post("/earn")
    async def earn_gold(
        request: Request,
        name: Annotated[str | None, Form()] = None,
        amount: Annotated[str, Form()] = "0",
        reason: Annotated[str, Form()] = "Treasure haul",
        category: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            return redirect_with_message(request, "Select a character to award loot to.", "error")
        amt = (amount or "0").strip() or "0"
        reason_text = (reason or "Treasure haul").strip() or "Treasure haul"
        try:
            category_enum = parse_category(category)
            txn = bank.earn_gold(cleaned_name, amt, description=reason_text, category=category_enum)
        except (ValueError, CharacterNotFoundError) as exc:
            return redirect_with_message(request, str(exc), "error")
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                f"{cleaned_name} gained {format_gp(txn.amount)} for {txn.description}.",
                "success",
            )

    @app.post("/spend")
    async def spend_gold(
        request: Request,
        name: Annotated[str | None, Form()] = None,
        amount: Annotated[str, Form()] = "0",
        reason: Annotated[str, Form()] = "Purchase",
        category: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            return redirect_with_message(request, "Select a character to spend from.", "error")
        amt = (amount or "0").strip() or "0"
        reason_text = (reason or "Purchase").strip() or "Purchase"
        try:
            category_enum = parse_category(category)
            txn = bank.spend_gold(cleaned_name, amt, description=reason_text, category=category_enum)
        except (ValueError, CharacterNotFoundError, InsufficientFundsError) as exc:
            return redirect_with_message(request, str(exc), "error")
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                f"{cleaned_name} spent {format_gp(txn.amount)} on {txn.description}.",
                "success",
            )

    @app.post("/transfer")
    async def transfer_gold(
        request: Request,
        source: Annotated[str | None, Form()] = None,
        target: Annotated[str | None, Form()] = None,
        amount: Annotated[str, Form()] = "0",
        reason: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        source_name = (source or "").strip()
        target_name = (target or "").strip()
        if not source_name or not target_name:
            return redirect_with_message(request, "Select both source and target characters.", "error")
        amt = (amount or "0").strip() or "0"
        note = (reason or "").strip() or None
        try:
            bank.transfer_gold(source_name, target_name, amt, description=note)
        except (ValueError, CharacterNotFoundError, InsufficientFundsError) as exc:
            return redirect_with_message(request, str(exc), "error")
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                f"Transferred {format_gp(amt)} from {source_name} to {target_name}.",
                "success",
            )

    @app.post("/distribute")
    async def distribute_loot(
        request: Request,
        characters: Annotated[list[str], Form(...)],
        amount: Annotated[str, Form()] = "0",
        reason: Annotated[str, Form()] = "Split loot",
        category: Annotated[str | None, Form()] = "loot",
    ) -> RedirectResponse:
        bank = load_bank()
        selected = [name.strip() for name in characters if name.strip()]
        if not selected:
            return redirect_with_message(
                request,
                "Select at least one adventurer to split loot amongst.",
                "error",
            )
        amt = (amount or "0").strip() or "0"
        reason_text = (reason or "Split loot").strip() or "Split loot"
        try:
            category_enum = parse_category(category) or EventCategory.LOOT
            bank.distribute_loot(
                selected,
                total_amount=amt,
                description=reason_text,
                category=category_enum,
            )
        except (ValueError, CharacterNotFoundError) as exc:
            return redirect_with_message(request, str(exc), "error")
        else:
            save_bank(bank)
            joined = ", ".join(selected)
            return redirect_with_message(
                request,
                f"Split {format_gp(amt)} across {joined}.",
                "success",
            )

    return app


def main() -> None:  # pragma: no cover - convenience entry point
    import uvicorn

    uvicorn.run("dndbank.web:create_app", factory=True, reload=False)


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    main()
