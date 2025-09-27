"""Client helpers for the public Open5e API."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://api.open5e.com/v2"


class Open5eError(RuntimeError):
    """Raised when the Open5e API cannot be contacted successfully."""


@dataclass(slots=True)
class Open5eItem:
    """Normalized representation of an item returned by the Open5e API."""

    name: str
    description: str | None
    category: str | None
    value_gp: str | None
    weight_lb: str | None
    weight_unit: str | None
    rarity: str | None
    document: str | None

    def to_payload(self) -> dict[str, str | None]:
        """Serialize the item into a JSON-friendly payload."""

        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "value_gp": self.value_gp,
            "weight_lb": self.weight_lb,
            "weight_unit": self.weight_unit,
            "rarity": self.rarity,
            "document": self.document,
        }


class Open5eClient:
    """Small wrapper around the Open5e REST API."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        user_agent: str = "dndbank/0.2 (+https://open5e.com)",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._headers = {"Accept": "application/json", "User-Agent": user_agent}

    async def search_items(
        self,
        query: str,
        *,
        limit: int = 8,
        transport: httpx.BaseTransport | None = None,
    ) -> list[Open5eItem]:
        """Search for equipment and inventory items."""

        cleaned = query.strip()
        if not cleaned:
            return []

        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout,
            transport=transport,
        ) as client:
            try:
                response = await client.get(
                    "/items/",
                    params={"search": cleaned, "limit": limit},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:  # pragma: no cover - exercised via tests
                raise Open5eError("Unable to reach the Open5e API") from exc

        data = response.json()
        items = data.get("results", [])
        return [self._parse_item(raw) for raw in items]

    def _parse_item(self, raw: dict[str, Any]) -> Open5eItem:
        category = self._extract_name(raw.get("category"))
        document = self._extract_name(raw.get("document"))
        return Open5eItem(
            name=raw.get("name", "Unknown Item"),
            description=(raw.get("desc") or None),
            category=category,
            value_gp=self._format_currency(raw.get("cost")),
            weight_lb=self._format_weight(raw.get("weight")),
            weight_unit=(raw.get("weight_unit") or None),
            rarity=(raw.get("rarity") or None),
            document=document,
        )

    @staticmethod
    def _extract_name(value: Any) -> str | None:
        if isinstance(value, dict):
            name = value.get("name")
            return name or None
        return value or None

    @staticmethod
    def _format_currency(raw: Any) -> str | None:
        if raw in (None, ""):
            return None
        try:
            amount = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return None
        normalized = amount.quantize(Decimal("0.01"))
        return f"{normalized}"

    @staticmethod
    def _format_weight(raw: Any) -> str | None:
        if raw in (None, ""):
            return None
        try:
            weight = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return None
        normalized = weight.normalize()
        text = format(normalized, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"


__all__ = ["Open5eClient", "Open5eError", "Open5eItem"]

