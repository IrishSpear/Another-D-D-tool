# Another D&D Tool

This project mirrors the structure of the original [KidBank](https://github.com/IrishSpear/kidbank) app while focusing on tabletop parties instead of kids' allowances. It ships as a Python package with well-tested domain objects, a high-level service façade, and a lightweight CLI for persisting gold ledgers to disk.

## Project structure

```
src/
  dndbank/
    __init__.py        # Public exports (DnDBank, models, exceptions)
    account.py         # CharacterAccount domain logic
    cli.py             # Argparse CLI for working with JSON ledgers
    exceptions.py      # Error hierarchy
    models.py          # Dataclasses and enums describing transactions
    money.py           # Decimal helpers for gold piece arithmetic
    service.py         # DnDBank façade coordinating accounts
pytest.ini             # Configures pytest to discover src/ package
tests/
  test_account.py      # Unit tests for CharacterAccount behaviour
  test_service.py      # Integration tests for the DnDBank façade
```

## Installation

The package only depends on the Python standard library. Python 3.10 or newer is recommended to match the typing used throughout the project.

Optionally create and activate a virtual environment, then install the project in editable mode for easier experimentation:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Running the test suite

Run the included tests (modelled after KidBank's coverage) with:

```bash
python -m pytest
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
