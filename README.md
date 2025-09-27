# Another D&D Tool

This project mirrors the structure of the original [KidBank](https://github.com/IrishSpear/kidbank) app while focusing on tabletop parties instead of kids' allowances. It now ships with a FastAPI-powered campaign console, well-tested domain objects, a high-level service façade, and a lightweight CLI for persisting gold ledgers to disk. Beyond party finances, the toolkit tracks character sheets, hit points, equipment, encounters, quests, party notes, and generic resource pools so you can run an entire 5e session from one place.

## Project structure

```
src/
  dndbank/
    __init__.py        # Public exports (DnDBank, models, exceptions)
    account.py         # CharacterAccount domain logic (gold, sheets, inventory)
    cli.py             # Argparse CLI for working with JSON ledgers
    exceptions.py      # Error hierarchy
    models.py          # Dataclasses and enums describing transactions, sheets, items
    money.py           # Decimal helpers for gold piece arithmetic
    service.py         # DnDBank façade coordinating accounts
pytest.ini             # Configures pytest to discover src/ package
tests/
  test_account.py      # Unit tests for CharacterAccount behaviour
  test_service.py      # Integration tests for the DnDBank façade
```

## Installation

Python 3.10 or newer is recommended to match the typing used throughout the project. Install the package (and its web
dependencies such as Uvicorn) before attempting to start the server:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Running the test suite

Run the included tests (modelled after KidBank's coverage) with:

```bash
python -m pytest
```

## Running the web app

Launch the KidBank-style dashboard with any ASGI server. Using Uvicorn (installed alongside the package) mirrors the original KidBank experience while persisting the ledger JSON to `instance/dnd_ledger.json` by default:

```bash
uvicorn dndbank.web:create_app --factory --reload
```

Once running, visit http://127.0.0.1:8000/ to manage every facet of the party. The dashboard is organised into tabs:

* **Ledger** – award loot, log expenses, split treasure, and transfer gold with a live transaction feed.
* **Character Sheets** – edit ancestry, class, ability scores, hit points, and free-form notes for each hero.
* **Inventory** – track equipment, consumables, treasure, and whether each item is equipped. Start typing an item name to search the [Open5e API](https://github.com/open5e/open5e-api) and auto-fill description, value, and weight data.
* **Combat Tracker** – build encounters, manage initiative order, advance rounds, and monitor conditions.
* **Party & Mechanics** – log quests, maintain shared notes, and manage resource pools for spell slots, hit dice, crew supplies, or other custom trackers.

Status banners confirm successful actions or highlight validation issues, and every form remembers the tab you submitted it from so workflow stays uninterrupted.

To customise persistence, override the ledger path when constructing the app yourself:

```python
from dndbank import create_app

app = create_app({"LEDGER_PATH": "/path/to/ledger.json"})
```

## Using the CLI

The CLI lives alongside the package and persists data in a JSON file (default `dnd_ledger.json`). Invoke it via the module entry point:

```bash
python -m dndbank.cli --help
```


### Create characters

```bash
python -m dndbank.cli create "Sir Galahad" --player "Alice" --gold 50
python -m dndbank.cli create "Mira Quickstep" --player "Bob"

```

### Record treasure and expenses

```bash
python -m dndbank.cli earn "Sir Galahad" 250 --reason "Dragon hoard"
python -m dndbank.cli spend "Mira Quickstep" 25 --reason "Thieves' guild dues"
python -m dndbank.cli transfer "Sir Galahad" "Mira Quickstep" 50 --reason "Shared spoils"
python -m dndbank.cli distribute 120 "Sir Galahad" "Mira Quickstep" --reason "Chest of coins"

```

### Check balances and history

```bash
python -m dndbank.cli status               # Show everyone
python -m dndbank.cli status "Mira Quickstep"  # Show one character
python -m dndbank.cli history "Mira Quickstep"
```

Because the ledger file is plain JSON you can commit it to version control or copy it between machines to keep a party's finances synchronised.

### Track character sheets and inventory

Use the new ``sheet`` command to view or update a character's role-playing information, ability scores, and hit points:

```bash
python -m dndbank.cli sheet "Sir Galahad" --class Paladin --ancestry Human --level 5 \
    --ability str=18 --ability cha=16 --hit-points maximum=45 --hit-points current=38
```

Manage equipment, consumables, and treasures with the ``inventory`` commands:

```bash
python -m dndbank.cli inventory add "Sir Galahad" "Longsword" --category Weapon --equipped
python -m dndbank.cli inventory list "Sir Galahad"
python -m dndbank.cli inventory update "Sir Galahad" "Longsword" --description "Family heirloom"
python -m dndbank.cli inventory remove "Sir Galahad" "Longsword"
```

### Browse 5e SRD reference data

Clone the [5e-bits/5e-database](https://github.com/5e-bits/5e-database) repository alongside this
project to enrich the toolkit with SRD compendium data. Point the CLI at the checkout using the
``--compendium-root`` flag to search spells, items, classes, and more:

```bash
git clone https://github.com/5e-bits/5e-database.git
python -m dndbank.cli --compendium-root ./5e-database compendium search equipment longsword
python -m dndbank.cli --compendium-root ./5e-database compendium show spells fireball
```

When adding or updating inventory entries you can prefill their description, weight, and cost from
the SRD data:

```bash
python -m dndbank.cli --compendium-root ./5e-database inventory add \
    "Sir Galahad" "Longsword" --from-compendium longsword --equipped
```

