from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dndbank.web import create_app


def make_app(tmp_path: Path):
    ledger = tmp_path / "ledger.json"
    app = create_app({"LEDGER_PATH": ledger})
    return app, ledger


def test_dashboard_renders_without_characters(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "No adventurers yet" in response.text


def test_full_web_flow_persists_to_ledger(tmp_path):
    app, ledger = make_app(tmp_path)
    client = TestClient(app)

    client.post(
        "/characters",
        data={"name": "Aria", "player": "Alice", "starting_gold": "100"},
        follow_redirects=True,
    )
    client.post(
        "/characters",
        data={"name": "Borin", "player": "", "starting_gold": "0"},
        follow_redirects=True,
    )
    client.post(
        "/earn",
        data={"name": "Aria", "amount": "50", "reason": "Quest reward", "category": "quest"},
        follow_redirects=True,
    )
    client.post(
        "/spend",
        data={"name": "Aria", "amount": "10", "reason": "Potion", "category": "purchase"},
        follow_redirects=True,
    )
    client.post(
        "/transfer",
        data={"source": "Aria", "target": "Borin", "amount": "25", "reason": "Share"},
        follow_redirects=True,
    )
    client.post(
        "/distribute",
        data={
            "characters": ["Aria", "Borin"],
            "amount": "20",
            "reason": "Loot split",
            "category": "loot",
        },
        follow_redirects=True,
    )

    assert ledger.exists()
    data = json.loads(ledger.read_text())
    characters = {entry["name"]: entry for entry in data["characters"]}

    assert characters["Aria"]["balance"] == "125.00"
    assert characters["Borin"]["balance"] == "35.00"

    response = client.get("/")
    body = response.text
    assert "Aria" in body
    assert "Borin" in body
    assert "125.00 gp" in body
    assert "35.00 gp" in body


def test_invalid_form_shows_error(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/earn",
        data={"name": "", "amount": "5"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Select a character to award loot to." in response.text
