"""High-level facade for orchestrating character accounts."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from .account import CharacterAccount
from .exceptions import CharacterAlreadyExistsError, CharacterNotFoundError
from .models import (
    AbilityScores,
    CharacterSheet,
    CombatEncounter,
    Combatant,
    EventCategory,
    HitPointPool,
    InventoryItem,
    PartyNote,
    QuestEntry,
    QuestStatus,
    ResourceTrack,
    Transaction,
)
from .money import AmountLike, to_decimal


class DnDBank:
    """Manage a party's collection of ``CharacterAccount`` objects."""

    __slots__ = (
        "_accounts",
        "_quests",
        "_party_notes",
        "_resources",
        "_encounters",
        "_active_encounter",
    )

    @classmethod
    def from_serialized(cls, payload: Mapping[str, object]) -> "DnDBank":
        bank = cls()
        for raw in payload.get("characters", []):
            account = CharacterAccount.from_serialized(raw)
            bank._accounts[account.name] = account
        for raw_quest in payload.get("quests", []):
            quest = QuestEntry.from_dict(raw_quest)
            bank._quests[quest.uid] = quest
        for raw_note in payload.get("party_notes", []):
            bank._party_notes.append(PartyNote.from_dict(raw_note))
        for raw_resource in payload.get("resources", []):
            resource = ResourceTrack.from_dict(raw_resource)
            bank._resources[resource.uid] = resource
        active_uid = payload.get("active_encounter")
        for raw_encounter in payload.get("encounters", []):
            encounter = CombatEncounter.from_dict(raw_encounter)
            bank._encounters[encounter.uid] = encounter
        bank._active_encounter = active_uid if isinstance(active_uid, str) and active_uid in bank._encounters else None
        return bank

    def __init__(self) -> None:
        self._accounts: dict[str, CharacterAccount] = {}
        self._quests: dict[str, QuestEntry] = {}
        self._party_notes: list[PartyNote] = []
        self._resources: dict[str, ResourceTrack] = {}
        self._encounters: dict[str, CombatEncounter] = {}
        self._active_encounter: str | None = None

    def list_characters(self) -> Tuple[str, ...]:
        """Return character names in alphabetical order."""

        return tuple(sorted(self._accounts))

    def create_character(
        self,
        name: str,
        *,
        player: str | None = None,
        starting_gold: AmountLike = 0,
        sheet: CharacterSheet | None = None,
    ) -> CharacterAccount:
        if name in self._accounts:
            raise CharacterAlreadyExistsError(f"Character '{name}' already exists.")
        account = CharacterAccount(
            name,
            player=player,
            starting_gold=starting_gold,
            sheet=sheet,
        )
        self._accounts[name] = account
        return account

    def get_character(self, name: str) -> CharacterAccount:
        try:
            return self._accounts[name]
        except KeyError as exc:
            raise CharacterNotFoundError(name) from exc

    def earn_gold(
        self,
        name: str,
        amount: AmountLike,
        description: str = "Treasure haul",
        *,
        category: EventCategory | None = None,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> Transaction:
        character = self.get_character(name)
        return character.earn(amount, description, category=category, metadata=metadata)

    def spend_gold(
        self,
        name: str,
        amount: AmountLike,
        description: str = "Purchase",
        *,
        category: EventCategory | None = None,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> Transaction:
        character = self.get_character(name)
        return character.spend(amount, description, category=category, metadata=metadata)

    def transfer_gold(
        self,
        source: str,
        target: str,
        amount: AmountLike,
        description: str | None = None,
        *,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> tuple[Transaction, Transaction]:
        source_account = self.get_character(source)
        target_account = self.get_character(target)
        if source_account is target_account:
            raise ValueError("Cannot transfer to the same character.")
        return source_account.transfer_to(
            target_account,
            amount,
            description,
            metadata=metadata,
        )

    def distribute_loot(
        self,
        names: Iterable[str],
        *,
        total_amount: AmountLike,
        description: str = "Split loot",
        category: EventCategory = EventCategory.LOOT,
    ) -> tuple[Transaction, ...]:
        accounts = [self.get_character(name) for name in names]
        if not accounts:
            return tuple()

        total_value = to_decimal(total_amount)
        share = (total_value / len(accounts)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        remainder = total_value - (share * len(accounts))

        transactions: list[Transaction] = []
        for account in accounts:
            top_up = Decimal("0")
            if remainder > Decimal("0"):
                top_up = Decimal("0.01")
                remainder -= top_up
            transactions.append(
                account.earn(
                    share + top_up,
                    description,
                    category=category,
                    metadata={"distribution": "loot"},
                )
            )
        return tuple(transactions)

    def to_serialized(self) -> dict[str, object]:
        return {
            "characters": [
                self._accounts[name].to_serialized() for name in self.list_characters()
            ],
            "quests": [quest.as_dict() for quest in self._quests.values()],
            "party_notes": [note.as_dict() for note in self._party_notes],
            "resources": [resource.as_dict() for resource in self._resources.values()],
            "encounters": [encounter.as_dict() for encounter in self._encounters.values()],
            "active_encounter": self._active_encounter,
        }

    # Character sheet management -------------------------------------------------

    def get_character_sheet(self, name: str) -> CharacterSheet:
        return self.get_character(name).sheet

    def update_character_sheet(self, name: str, **fields: object) -> CharacterSheet:
        account = self.get_character(name)
        return account.update_sheet(**fields)

    def set_ability_scores(self, name: str, **scores: int) -> AbilityScores:
        account = self.get_character(name)
        return account.set_ability_scores(**scores)

    def adjust_hit_points(
        self,
        name: str,
        delta: int,
        *,
        use_temporary: bool = True,
    ) -> HitPointPool:
        account = self.get_character(name)
        return account.adjust_hit_points(delta, use_temporary=use_temporary)

    def set_hit_points(
        self,
        name: str,
        *,
        maximum: int | None = None,
        current: int | None = None,
        temporary: int | None = None,
    ) -> HitPointPool:
        account = self.get_character(name)
        return account.set_hit_points(maximum=maximum, current=current, temporary=temporary)

    # Inventory management -------------------------------------------------------

    def list_inventory(self, name: str) -> Tuple[InventoryItem, ...]:
        account = self.get_character(name)
        return account.list_inventory()

    def add_inventory_item(
        self,
        name: str,
        *,
        item_name: str,
        quantity: int = 1,
        description: str | None = None,
        weight: float | None = None,
        value_gp: AmountLike | None = None,
        category: str | None = None,
        equipped: bool | None = None,
    ) -> InventoryItem:
        account = self.get_character(name)
        return account.add_inventory_item(
            item_name,
            quantity=quantity,
            description=description,
            weight=weight,
            value_gp=value_gp,
            category=category,
            equipped=equipped,
        )

    def update_inventory_item(
        self,
        name: str,
        item_name: str,
        *,
        quantity: int | None = None,
        description: str | None = None,
        weight: float | None = None,
        value_gp: AmountLike | None = None,
        category: str | None = None,
        equipped: bool | None = None,
    ) -> InventoryItem:
        account = self.get_character(name)
        return account.update_inventory_item(
            item_name,
            quantity=quantity,
            description=description,
            weight=weight,
            value_gp=value_gp,
            category=category,
            equipped=equipped,
        )

    def remove_inventory_item(
        self,
        name: str,
        item_name: str,
        *,
        quantity: int | None = None,
    ) -> None:
        account = self.get_character(name)
        account.remove_inventory_item(item_name, quantity=quantity)

    # Quest log management -------------------------------------------------------

    def list_quests(self) -> Tuple[QuestEntry, ...]:
        return tuple(sorted(self._quests.values(), key=lambda quest: quest.last_updated, reverse=True))

    def add_quest(
        self,
        title: str,
        *,
        summary: str = "",
        reward: str | None = None,
        status: QuestStatus | str = QuestStatus.ACTIVE,
    ) -> QuestEntry:
        quest = QuestEntry(
            title=title,
            summary=summary,
            reward=reward,
            status=status if isinstance(status, QuestStatus) else QuestStatus(str(status)),
        )
        self._quests[quest.uid] = quest
        return quest

    def update_quest(
        self,
        uid: str,
        *,
        title: str | None = None,
        summary: str | None = None,
        reward: str | None = None,
        status: QuestStatus | str | None = None,
    ) -> QuestEntry:
        if uid not in self._quests:
            raise KeyError(f"Quest with id '{uid}' does not exist.")
        quest = self._quests[uid]
        quest.update(title=title, summary=summary, reward=reward, status=status)
        return quest

    def remove_quest(self, uid: str) -> None:
        if uid not in self._quests:
            raise KeyError(f"Quest with id '{uid}' does not exist.")
        del self._quests[uid]

    # Party notes ----------------------------------------------------------------

    def list_party_notes(self) -> Tuple[PartyNote, ...]:
        return tuple(sorted(self._party_notes, key=lambda note: note.created_at, reverse=True))

    def add_party_note(self, title: str, body: str, *, category: str = "general") -> PartyNote:
        note = PartyNote(title=title, body=body, category=category)
        self._party_notes.append(note)
        return note

    def remove_party_note(self, uid: str) -> None:
        for index, note in enumerate(self._party_notes):
            if note.uid == uid:
                del self._party_notes[index]
                return
        raise KeyError(f"Party note with id '{uid}' does not exist.")

    # Resource trackers ----------------------------------------------------------

    def list_resources(self) -> Tuple[ResourceTrack, ...]:
        return tuple(self._resources.values())

    def add_resource(
        self,
        name: str,
        *,
        current: int,
        maximum: int | None = None,
        notes: str | None = None,
    ) -> ResourceTrack:
        resource = ResourceTrack(name=name, current=current, maximum=maximum, notes=notes)
        self._resources[resource.uid] = resource
        return resource

    def update_resource(
        self,
        uid: str,
        *,
        current: int | None = None,
        maximum: int | None = None,
        notes: str | None = None,
    ) -> ResourceTrack:
        if uid not in self._resources:
            raise KeyError(f"Resource with id '{uid}' does not exist.")
        resource = self._resources[uid]
        resource.update(current=current, maximum=maximum, notes=notes)
        return resource

    def adjust_resource(self, uid: str, delta: int) -> ResourceTrack:
        if uid not in self._resources:
            raise KeyError(f"Resource with id '{uid}' does not exist.")
        resource = self._resources[uid]
        return resource.adjust(delta)

    def remove_resource(self, uid: str) -> None:
        if uid not in self._resources:
            raise KeyError(f"Resource with id '{uid}' does not exist.")
        del self._resources[uid]

    # Combat encounter management -------------------------------------------------

    def list_encounters(self) -> Tuple[CombatEncounter, ...]:
        return tuple(self._encounters.values())

    def get_encounter(self, uid: str) -> CombatEncounter:
        if uid not in self._encounters:
            raise KeyError(f"Encounter with id '{uid}' does not exist.")
        return self._encounters[uid]

    def get_active_encounter(self) -> CombatEncounter | None:
        if self._active_encounter and self._active_encounter in self._encounters:
            return self._encounters[self._active_encounter]
        return None

    def create_encounter(
        self,
        name: str,
        *,
        environment: str | None = None,
        notes: str | None = None,
    ) -> CombatEncounter:
        encounter = CombatEncounter(name=name, environment=environment, notes=notes)
        self._encounters[encounter.uid] = encounter
        self._active_encounter = encounter.uid
        return encounter

    def update_encounter(
        self,
        uid: str,
        *,
        name: str | None = None,
        environment: str | None = None,
        notes: str | None = None,
    ) -> CombatEncounter:
        encounter = self.get_encounter(uid)
        if name is not None:
            encounter.name = name
        if environment is not None:
            encounter.environment = environment
        if notes is not None:
            encounter.notes = notes
        return encounter

    def set_active_encounter(self, uid: str | None) -> None:
        if uid is None:
            self._active_encounter = None
        elif uid in self._encounters:
            self._active_encounter = uid
        else:
            raise KeyError(f"Encounter with id '{uid}' does not exist.")

    def remove_encounter(self, uid: str) -> None:
        if uid not in self._encounters:
            raise KeyError(f"Encounter with id '{uid}' does not exist.")
        del self._encounters[uid]
        if self._active_encounter == uid:
            self._active_encounter = None

    def add_combatant(
        self,
        encounter_uid: str,
        *,
        name: str,
        initiative: int,
        armor_class: int | None = None,
        maximum_hp: int | None = None,
        current_hp: int | None = None,
        conditions: Sequence[str] | None = None,
        role: str | None = None,
        notes: str | None = None,
        player_character: bool | None = None,
    ) -> Combatant:
        encounter = self.get_encounter(encounter_uid)
        roster = {combatant.name.casefold(): combatant for combatant in encounter.combatants}
        key = name.casefold()
        if key in roster:
            combatant = roster[key]
            combatant.update(
                initiative=initiative,
                armor_class=armor_class,
                maximum_hp=maximum_hp,
                current_hp=current_hp,
                conditions=conditions,
                role=role,
                notes=notes,
                player_character=player_character,
            )
        else:
            combatant = Combatant(
                name=name,
                initiative=initiative,
                armor_class=armor_class,
                maximum_hp=maximum_hp,
                current_hp=current_hp,
                conditions=tuple(conditions or ()),
                role=role,
                notes=notes,
                player_character=bool(player_character),
            )
            roster[key] = combatant
        encounter.combatants = tuple(
            sorted(roster.values(), key=lambda entry: (-entry.initiative, entry.name.casefold()))
        )
        if encounter.active_index >= len(encounter.combatants):
            encounter.active_index = 0
        return combatant

    def remove_combatant(self, encounter_uid: str, *, name: str) -> None:
        encounter = self.get_encounter(encounter_uid)
        filtered = [combatant for combatant in encounter.combatants if combatant.name.casefold() != name.casefold()]
        if len(filtered) == len(encounter.combatants):
            raise KeyError(f"Combatant '{name}' is not part of the encounter.")
        encounter.combatants = tuple(filtered)
        if encounter.active_index >= len(encounter.combatants):
            encounter.active_index = 0

    def advance_encounter(self, encounter_uid: str) -> CombatEncounter:
        encounter = self.get_encounter(encounter_uid)
        if not encounter.combatants:
            return encounter
        encounter.active_index = (encounter.active_index + 1) % len(encounter.combatants)
        if encounter.active_index == 0:
            encounter.round += 1
        return encounter

    def reset_encounter(self, encounter_uid: str) -> CombatEncounter:
        encounter = self.get_encounter(encounter_uid)
        encounter.round = 1
        encounter.active_index = 0
        return encounter
