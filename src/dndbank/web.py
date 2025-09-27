"""FastAPI-powered web interface that mirrors the KidBank experience."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Annotated, Sequence
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .exceptions import (
    CharacterAlreadyExistsError,
    CharacterNotFoundError,
    InsufficientFundsError,
)
from .models import EventCategory, QuestStatus
from .money import format_gp
from .open5e import Open5eClient, Open5eError
from .service import DnDBank


LEDGER_TAB = "ledger"
SHEETS_TAB = "sheets"
INVENTORY_TAB = "inventory"
COMBAT_TAB = "combat"
PARTY_TAB = "party"


def create_app(config: dict[str, Any] | None = None) -> FastAPI:
    """Create and configure the KidBank-style D&D ledger web app."""

    package_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(package_dir / "templates"))
    templates.env.filters["format_gp"] = format_gp

    app = FastAPI(title="D&D Bank", version="0.2.0")
    open5e_client = Open5eClient()

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

    @app.get("/api/open5e/items")
    async def search_open5e_items(q: str, limit: int = 8) -> JSONResponse:
        clamped_limit = max(1, min(limit, 20))
        try:
            results = await open5e_client.search_items(q, limit=clamped_limit)
        except Open5eError:
            return JSONResponse({"results": []}, status_code=502)
        return JSONResponse({"results": [item.to_payload() for item in results]})

    def redirect_with_message(
        request: Request,
        message: str,
        category: str,
        *,
        tab: str | None = None,
    ) -> RedirectResponse:
        target = request.url_for("dashboard")
        params: list[tuple[str, str]] = [("message", message), ("category", category)]
        if tab:
            params.append(("tab", tab))
        query = urlencode(params)
        return RedirectResponse(url=f"{target}?{query}", status_code=303)

    def parse_category(raw: str | None) -> EventCategory | None:
        value = (raw or "").strip()
        if not value:
            return None
        try:
            return EventCategory(value)
        except ValueError as exc:
            raise ValueError(f"Unknown category '{value}'.") from exc

    def parse_int(raw: str | None) -> int | None:
        if raw is None:
            return None
        cleaned = raw.strip()
        if not cleaned:
            return None
        return int(cleaned)

    def parse_float(raw: str | None) -> float | None:
        if raw is None:
            return None
        cleaned = raw.strip()
        if not cleaned:
            return None
        return float(cleaned)

    def parse_bool(raw: str | None) -> bool:
        if raw is None:
            return False
        cleaned = raw.strip().lower()
        return cleaned in {"on", "true", "1", "yes"}

    def parse_conditions(raw: str | None) -> Sequence[str] | None:
        if raw is None:
            return None
        values = [segment.strip() for segment in raw.split(",")]
        return [segment for segment in values if segment]

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
                    "sheet": account.sheet,
                    "inventory": account.list_inventory(),
                    "transactions": history,
                }
            )
        active_tab = request.query_params.get("tab", LEDGER_TAB)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "request": request,
                "characters": characters,
                "total_balance": total,
                "messages": to_messages(request),
                "categories": list(EventCategory),
                "active_tab": active_tab,
                "quests": bank.list_quests(),
                "notes": bank.list_party_notes(),
                "resources": bank.list_resources(),
                "encounters": bank.list_encounters(),
                "active_encounter": bank.get_active_encounter(),
                "quest_statuses": list(QuestStatus),
            },
        )

    @app.post("/characters")
    async def create_character(
        request: Request,
        name: Annotated[str, Form(...)],
        player: Annotated[str | None, Form()] = None,
        starting_gold: Annotated[str, Form()] = "0",
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_name = name.strip()
        cleaned_player = (player or "").strip() or None
        starting = (starting_gold or "0").strip() or "0"
        if not cleaned_name:
            return redirect_with_message(request, "Character name is required.", "error", tab=tab or LEDGER_TAB)
        try:
            bank.create_character(cleaned_name, player=cleaned_player, starting_gold=starting)
        except CharacterAlreadyExistsError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or LEDGER_TAB)
        except ValueError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or LEDGER_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, f"Created {cleaned_name}.", "success", tab=tab or LEDGER_TAB)

    @app.post("/earn")
    async def earn_gold(
        request: Request,
        name: Annotated[str | None, Form()] = None,
        amount: Annotated[str, Form()] = "0",
        reason: Annotated[str, Form()] = "Treasure haul",
        category: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            return redirect_with_message(
                request,
                "Select a character to award loot to.",
                "error",
                tab=tab or LEDGER_TAB,
            )
        amt = (amount or "0").strip() or "0"
        reason_text = (reason or "Treasure haul").strip() or "Treasure haul"
        try:
            category_enum = parse_category(category)
            txn = bank.earn_gold(cleaned_name, amt, description=reason_text, category=category_enum)
        except (ValueError, CharacterNotFoundError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or LEDGER_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                f"{cleaned_name} gained {format_gp(txn.amount)} for {txn.description}.",
                "success",
                tab=tab or LEDGER_TAB,
            )

    @app.post("/spend")
    async def spend_gold(
        request: Request,
        name: Annotated[str | None, Form()] = None,
        amount: Annotated[str, Form()] = "0",
        reason: Annotated[str, Form()] = "Purchase",
        category: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            return redirect_with_message(
                request,
                "Select a character to log spending for.",
                "error",
                tab=tab or LEDGER_TAB,
            )
        amt = (amount or "0").strip() or "0"
        reason_text = (reason or "Purchase").strip() or "Purchase"
        try:
            category_enum = parse_category(category)
            txn = bank.spend_gold(cleaned_name, amt, description=reason_text, category=category_enum)
        except (ValueError, CharacterNotFoundError, InsufficientFundsError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or LEDGER_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                f"{cleaned_name} spent {format_gp(txn.amount)} on {txn.description}.",
                "success",
                tab=tab or LEDGER_TAB,
            )

    @app.post("/transfer")
    async def transfer_gold(
        request: Request,
        source: Annotated[str | None, Form()] = None,
        target: Annotated[str | None, Form()] = None,
        amount: Annotated[str, Form()] = "0",
        reason: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        source_name = (source or "").strip()
        target_name = (target or "").strip()
        if not source_name or not target_name:
            return redirect_with_message(
                request,
                "Select a source and destination adventurer.",
                "error",
                tab=tab or LEDGER_TAB,
            )
        amt = (amount or "0").strip() or "0"
        note = (reason or "").strip() or None
        try:
            bank.transfer_gold(source_name, target_name, amt, description=note)
        except (ValueError, CharacterNotFoundError, InsufficientFundsError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or LEDGER_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                f"Transferred {format_gp(amt)} from {source_name} to {target_name}.",
                "success",
                tab=tab or LEDGER_TAB,
            )

    @app.post("/distribute")
    async def distribute_loot(
        request: Request,
        characters: Annotated[list[str], Form(...)],
        amount: Annotated[str, Form()] = "0",
        reason: Annotated[str, Form()] = "Split loot",
        category: Annotated[str | None, Form()] = "loot",
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        selected = [name.strip() for name in characters if name.strip()]
        if not selected:
            return redirect_with_message(
                request,
                "Select at least one adventurer to split loot amongst.",
                "error",
                tab=tab or LEDGER_TAB,
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
            return redirect_with_message(request, str(exc), "error", tab=tab or LEDGER_TAB)
        else:
            save_bank(bank)
            joined = ", ".join(selected)
            return redirect_with_message(
                request,
                f"Split {format_gp(amt)} across {joined}.",
                "success",
                tab=tab or LEDGER_TAB,
            )

    @app.post("/sheet/update")
    async def update_sheet(
        request: Request,
        name: Annotated[str, Form(...)],
        ancestry: Annotated[str | None, Form()] = None,
        character_class: Annotated[str | None, Form()] = None,
        background: Annotated[str | None, Form()] = None,
        alignment: Annotated[str | None, Form()] = None,
        level: Annotated[str | None, Form()] = None,
        experience: Annotated[str | None, Form()] = None,
        proficiency_bonus: Annotated[str | None, Form()] = None,
        inspiration: Annotated[str | None, Form()] = None,
        passive_perception: Annotated[str | None, Form()] = None,
        notes: Annotated[str | None, Form()] = None,
        strength: Annotated[str | None, Form()] = None,
        dexterity: Annotated[str | None, Form()] = None,
        constitution: Annotated[str | None, Form()] = None,
        intelligence: Annotated[str | None, Form()] = None,
        wisdom: Annotated[str | None, Form()] = None,
        charisma: Annotated[str | None, Form()] = None,
        hp_maximum: Annotated[str | None, Form()] = None,
        hp_current: Annotated[str | None, Form()] = None,
        hp_temporary: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_name = name.strip()
        if not cleaned_name:
            return redirect_with_message(
                request,
                "Character name is required to update the sheet.",
                "error",
                tab=tab or SHEETS_TAB,
            )
        fields: dict[str, object] = {}
        if ancestry is not None:
            fields["ancestry"] = ancestry or None
        if character_class is not None:
            fields["character_class"] = character_class or None
        if background is not None:
            fields["background"] = background or None
        if alignment is not None:
            fields["alignment"] = alignment or None
        if level is not None and level.strip():
            fields["level"] = int(level)
        if experience is not None and experience.strip():
            fields["experience"] = int(experience)
        if proficiency_bonus is not None and proficiency_bonus.strip():
            fields["proficiency_bonus"] = int(proficiency_bonus)
        if passive_perception is not None and passive_perception.strip():
            fields["passive_perception"] = int(passive_perception)
        if notes is not None:
            fields["notes"] = notes or None
        fields["inspiration"] = parse_bool(inspiration)

        ability_updates = {
            key: parse_int(value)
            for key, value in {
                "strength": strength,
                "dexterity": dexterity,
                "constitution": constitution,
                "intelligence": intelligence,
                "wisdom": wisdom,
                "charisma": charisma,
            }.items()
            if value not in (None, "", " ")
        }
        if ability_updates:
            fields["ability_scores"] = {key: value for key, value in ability_updates.items() if value is not None}

        hp_updates = {
            key: parse_int(value)
            for key, value in {
                "maximum": hp_maximum,
                "current": hp_current,
                "temporary": hp_temporary,
            }.items()
            if value not in (None, "", " ")
        }
        if hp_updates:
            fields["hit_points"] = {key: value for key, value in hp_updates.items() if value is not None}

        try:
            bank.update_character_sheet(cleaned_name, **fields)
        except (CharacterNotFoundError, ValueError, KeyError, TypeError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or SHEETS_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                f"Updated {cleaned_name}'s character sheet.",
                "success",
                tab=tab or SHEETS_TAB,
            )

    @app.post("/inventory/add")
    async def add_inventory(
        request: Request,
        character: Annotated[str, Form(...)],
        item_name: Annotated[str, Form(...)],
        quantity: Annotated[str | None, Form()] = "1",
        description: Annotated[str | None, Form()] = None,
        weight: Annotated[str | None, Form()] = None,
        value_gp: Annotated[str | None, Form()] = None,
        category: Annotated[str | None, Form()] = None,
        equipped: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        name_cleaned = character.strip()
        if not name_cleaned:
            return redirect_with_message(request, "Select a character.", "error", tab=tab or INVENTORY_TAB)
        item_cleaned = item_name.strip()
        if not item_cleaned:
            return redirect_with_message(request, "Item name cannot be blank.", "error", tab=tab or INVENTORY_TAB)
        try:
            qty = parse_int(quantity) or 1
            wt = parse_float(weight)
            value = (value_gp or "").strip() or None
            bank.add_inventory_item(
                name_cleaned,
                item_name=item_cleaned,
                quantity=qty,
                description=description or None,
                weight=wt,
                value_gp=value,
                category=(category or "").strip() or None,
                equipped=parse_bool(equipped),
            )
        except (CharacterNotFoundError, ValueError, KeyError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or INVENTORY_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                f"Updated {name_cleaned}'s inventory.",
                "success",
                tab=tab or INVENTORY_TAB,
            )

    @app.post("/inventory/remove")
    async def remove_inventory(
        request: Request,
        character: Annotated[str, Form(...)],
        item_name: Annotated[str, Form(...)],
        quantity: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        name_cleaned = character.strip()
        item_cleaned = item_name.strip()
        if not name_cleaned or not item_cleaned:
            return redirect_with_message(
                request,
                "Character and item must be provided.",
                "error",
                tab=tab or INVENTORY_TAB,
            )
        try:
            qty = parse_int(quantity)
            bank.remove_inventory_item(name_cleaned, item_cleaned, quantity=qty)
        except (CharacterNotFoundError, KeyError, ValueError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or INVENTORY_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                f"Removed {item_cleaned} from {name_cleaned}.",
                "success",
                tab=tab or INVENTORY_TAB,
            )

    @app.post("/quest/add")
    async def add_quest(
        request: Request,
        title: Annotated[str, Form(...)],
        summary: Annotated[str | None, Form()] = None,
        reward: Annotated[str | None, Form()] = None,
        status: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_title = title.strip()
        if not cleaned_title:
            return redirect_with_message(request, "Quest title cannot be blank.", "error", tab=tab or PARTY_TAB)
        try:
            quest_status = QuestStatus(status) if status else QuestStatus.ACTIVE
            bank.add_quest(
                cleaned_title,
                summary=(summary or "").strip(),
                reward=(reward or "").strip() or None,
                status=quest_status,
            )
        except ValueError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or PARTY_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                f"Logged quest '{cleaned_title}'.",
                "success",
                tab=tab or PARTY_TAB,
            )

    @app.post("/quest/status")
    async def update_quest_status(
        request: Request,
        quest_id: Annotated[str, Form(...)],
        status: Annotated[str, Form(...)],
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.update_quest(quest_id, status=QuestStatus(status))
        except (KeyError, ValueError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or PARTY_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(
                request,
                "Updated quest status.",
                "success",
                tab=tab or PARTY_TAB,
            )

    @app.post("/quest/delete")
    async def delete_quest(
        request: Request,
        quest_id: Annotated[str, Form(...)],
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.remove_quest(quest_id)
        except KeyError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or PARTY_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Removed quest.", "success", tab=tab or PARTY_TAB)

    @app.post("/notes/add")
    async def add_note(
        request: Request,
        title: Annotated[str, Form(...)],
        body: Annotated[str, Form(...)],
        category: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_title = title.strip()
        if not cleaned_title:
            return redirect_with_message(request, "Note title cannot be blank.", "error", tab=tab or PARTY_TAB)
        if not body.strip():
            return redirect_with_message(request, "Note body cannot be blank.", "error", tab=tab or PARTY_TAB)
        bank.add_party_note(cleaned_title, body.strip(), category=(category or "").strip() or "general")
        save_bank(bank)
        return redirect_with_message(request, "Added party note.", "success", tab=tab or PARTY_TAB)

    @app.post("/notes/delete")
    async def delete_note(
        request: Request,
        note_id: Annotated[str, Form(...)],
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.remove_party_note(note_id)
        except KeyError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or PARTY_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Removed party note.", "success", tab=tab or PARTY_TAB)

    @app.post("/resources/add")
    async def add_resource(
        request: Request,
        name: Annotated[str, Form(...)],
        current: Annotated[str, Form(...)],
        maximum: Annotated[str | None, Form()] = None,
        notes: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_name = name.strip()
        if not cleaned_name:
            return redirect_with_message(request, "Resource name cannot be blank.", "error", tab=tab or PARTY_TAB)
        try:
            bank.add_resource(
                cleaned_name,
                current=int(current),
                maximum=parse_int(maximum),
                notes=(notes or "").strip() or None,
            )
        except (ValueError, KeyError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or PARTY_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Added resource tracker.", "success", tab=tab or PARTY_TAB)

    @app.post("/resources/update")
    async def update_resource(
        request: Request,
        resource_id: Annotated[str, Form(...)],
        current: Annotated[str | None, Form()] = None,
        maximum: Annotated[str | None, Form()] = None,
        notes: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.update_resource(
                resource_id,
                current=parse_int(current),
                maximum=parse_int(maximum),
                notes=(notes or "").strip() or None,
            )
        except (ValueError, KeyError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or PARTY_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Updated resource tracker.", "success", tab=tab or PARTY_TAB)

    @app.post("/resources/adjust")
    async def adjust_resource(
        request: Request,
        resource_id: Annotated[str, Form(...)],
        delta: Annotated[str, Form(...)],
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.adjust_resource(resource_id, int(delta))
        except (ValueError, KeyError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or PARTY_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Adjusted resource tracker.", "success", tab=tab or PARTY_TAB)

    @app.post("/resources/delete")
    async def delete_resource(
        request: Request,
        resource_id: Annotated[str, Form(...)],
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.remove_resource(resource_id)
        except KeyError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or PARTY_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Removed resource tracker.", "success", tab=tab or PARTY_TAB)

    @app.post("/encounters/create")
    async def create_encounter(
        request: Request,
        name: Annotated[str, Form(...)],
        environment: Annotated[str | None, Form()] = None,
        notes: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_name = name.strip()
        if not cleaned_name:
            return redirect_with_message(request, "Encounter name cannot be blank.", "error", tab=tab or COMBAT_TAB)
        bank.create_encounter(cleaned_name, environment=(environment or "").strip() or None, notes=(notes or "").strip() or None)
        save_bank(bank)
        return redirect_with_message(request, f"Created encounter '{cleaned_name}'.", "success", tab=tab or COMBAT_TAB)

    @app.post("/encounters/activate")
    async def activate_encounter(
        request: Request,
        encounter_id: Annotated[str, Form(...)],
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.set_active_encounter(encounter_id)
        except KeyError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or COMBAT_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Set active encounter.", "success", tab=tab or COMBAT_TAB)

    @app.post("/encounters/delete")
    async def delete_encounter(
        request: Request,
        encounter_id: Annotated[str, Form(...)],
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.remove_encounter(encounter_id)
        except KeyError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or COMBAT_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Deleted encounter.", "success", tab=tab or COMBAT_TAB)

    @app.post("/encounters/advance")
    async def advance_encounter(
        request: Request,
        encounter_id: Annotated[str, Form(...)],
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.advance_encounter(encounter_id)
        except KeyError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or COMBAT_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Advanced initiative.", "success", tab=tab or COMBAT_TAB)

    @app.post("/encounters/reset")
    async def reset_encounter(
        request: Request,
        encounter_id: Annotated[str, Form(...)],
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.reset_encounter(encounter_id)
        except KeyError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or COMBAT_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Reset encounter.", "success", tab=tab or COMBAT_TAB)

    @app.post("/encounters/combatant")
    async def upsert_combatant(
        request: Request,
        encounter_id: Annotated[str, Form(...)],
        name: Annotated[str, Form(...)],
        initiative: Annotated[str, Form(...)],
        armor_class: Annotated[str | None, Form()] = None,
        maximum_hp: Annotated[str | None, Form()] = None,
        current_hp: Annotated[str | None, Form()] = None,
        conditions: Annotated[str | None, Form()] = None,
        role: Annotated[str | None, Form()] = None,
        notes: Annotated[str | None, Form()] = None,
        player_character: Annotated[str | None, Form()] = None,
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        cleaned_name = name.strip()
        if not cleaned_name:
            return redirect_with_message(request, "Combatant name cannot be blank.", "error", tab=tab or COMBAT_TAB)
        try:
            bank.add_combatant(
                encounter_id,
                name=cleaned_name,
                initiative=int(initiative),
                armor_class=parse_int(armor_class),
                maximum_hp=parse_int(maximum_hp),
                current_hp=parse_int(current_hp),
                conditions=parse_conditions(conditions),
                role=(role or "").strip() or None,
                notes=(notes or "").strip() or None,
                player_character=parse_bool(player_character),
            )
        except (KeyError, ValueError) as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or COMBAT_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Updated combatant.", "success", tab=tab or COMBAT_TAB)

    @app.post("/encounters/combatant/remove")
    async def remove_combatant(
        request: Request,
        encounter_id: Annotated[str, Form(...)],
        name: Annotated[str, Form(...)],
        tab: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        bank = load_bank()
        try:
            bank.remove_combatant(encounter_id, name=name)
        except KeyError as exc:
            return redirect_with_message(request, str(exc), "error", tab=tab or COMBAT_TAB)
        else:
            save_bank(bank)
            return redirect_with_message(request, "Removed combatant.", "success", tab=tab or COMBAT_TAB)

    return app


def main() -> None:  # pragma: no cover - convenience entry point
    import uvicorn

    uvicorn.run("dndbank.web:create_app", factory=True, reload=False)


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    main()
