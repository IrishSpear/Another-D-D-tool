from __future__ import annotations

import asyncio

import httpx
import pytest

from dndbank.open5e import Open5eClient, Open5eError


def test_search_items_normalizes_payload() -> None:
    payload = {
        "results": [
            {
                "name": "Acid",
                "desc": "A vial of acid.",
                "category": {"name": "Weapon"},
                "cost": "25.00",
                "weight": "1.000",
                "weight_unit": "lb",
                "rarity": None,
                "document": {"name": "SRD"},
            },
            {
                "name": "Alchemy Jug",
                "desc": "A wondrous item.",
                "category": {"name": "Wondrous item"},
                "cost": None,
                "weight": "12.50",
                "weight_unit": "lb",
                "rarity": "Uncommon",
                "document": {"name": "SRD"},
            },
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/items/")
        assert request.url.params.get("search") == "sword"
        assert request.url.params.get("limit") == "5"
        return httpx.Response(200, json=payload)

    client = Open5eClient()
    results = asyncio.run(
        client.search_items(" sword ", limit=5, transport=httpx.MockTransport(handler))
    )

    assert len(results) == 2
    first = results[0]
    assert first.name == "Acid"
    assert first.category == "Weapon"
    assert first.value_gp == "25.00"
    assert first.weight_lb == "1"
    assert first.document == "SRD"
    assert first.to_payload()["name"] == "Acid"


def test_search_items_blank_query_short_circuits() -> None:
    client = Open5eClient()
    results = asyncio.run(client.search_items("   "))
    assert results == []


def test_search_items_raises_when_api_unavailable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = Open5eClient()

    with pytest.raises(Open5eError):
        asyncio.run(client.search_items("wand", transport=httpx.MockTransport(handler)))
