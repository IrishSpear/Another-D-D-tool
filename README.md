# Another D&D Tool

This repository contains a small Kidbank-inspired ledger application written in
Python.  It helps Dungeon Masters keep track of each adventurer's gold balance
and the story behind every transaction.

## Features

* Create characters linked to specific players.
* Record earned treasure, spent gold, and transfers between party members.
* Persist data to a JSON file that can be version controlled or backed up.
* Inspect the party's current status or a character's history from the command
  line.

## Getting Started

The application has no third-party dependencies and runs with the standard
Python interpreter (3.9 or newer is recommended).

```bash
python app.py --help
```

This prints the available subcommands.  The examples below use the default
ledger file `dnd_ledger.json` in the current directory.

### Create characters

```bash
python app.py create "Sir Galahad" --player "Alice"
python app.py create "Mira Quickstep" --player "Bob"
```

### Record treasure and expenses

```bash
python app.py earn "Sir Galahad" 250 --reason "Dragon hoard"
python app.py spend "Mira Quickstep" 25 --reason "Thieves' guild dues"
python app.py transfer "Sir Galahad" "Mira Quickstep" 50 --reason "Shared spoils"
```

### Check balances and history

```bash
python app.py status           # Show everyone
python app.py status "Mira Quickstep"  # Show one character
python app.py history "Mira Quickstep"
```

The ledger file can be committed to the campaign repository or copied between
computers to keep your party's finances synchronized.

