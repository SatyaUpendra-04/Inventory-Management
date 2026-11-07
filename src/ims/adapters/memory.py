"""In-memory storage: the reference implementation of the storage ports.

Used for fast application tests and as the baseline every other adapter is compared
with in the contract tests. Not for production: nothing is persisted.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import Protocol

from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import ItemType
from ims.domain.assets.status import StatusEvent
from ims.domain.audit import AuditEntry
from ims.domain.common.errors import AlreadyExists, ConflictError, NotFound
from ims.domain.common.ids import AssetId, CommandId, ItemTypeId, UserId
from ims.domain.identity.user import User
from ims.domain.stock.ledger import StockMovement
from ims.domain.usage.ledger import UsageEntry
from ims.ports.repository import CommandRecord, Storage


class _Versioned(Protocol):
    @property
    def id(self) -> Hashable: ...
    @property
    def version(self) -> int: ...


class _Table[R: _Versioned]:
    """Versioned records with unique keys, mirroring the adapter contract."""

    def __init__(self, label: str, unique: dict[str, Callable[[R], Hashable | None]]) -> None:
        self._label = label
        self._unique = unique
        self.rows: dict[Hashable, R] = {}

    def add(self, record: R) -> None:
        if record.id in self.rows:
            raise AlreadyExists(f"{self._label} {record.id} already exists.")
        self._check_unique(record)
        self.rows[record.id] = record

    def update(self, record: R) -> None:
        stored = self.rows.get(record.id)
        if stored is None:
            raise NotFound(f"{self._label} {record.id} does not exist.")
        if stored.version != record.version - 1:
            raise ConflictError(
                f"This {self._label} was changed by someone else. Reload and try again."
            )
        self._check_unique(record)
        self.rows[record.id] = record

    def find(self, key: str, value: Hashable) -> R | None:
        extract = self._unique[key]
        return next((r for r in self.rows.values() if extract(r) == value), None)

    def _check_unique(self, record: R) -> None:
        for key, extract in self._unique.items():
            value = extract(record)
            if value is None:
                continue
            for other in self.rows.values():
                if other.id != record.id and extract(other) == value:
                    raise ConflictError(f"{key.replace('_', ' ')} is already in use.")


class _Stream[E]:
    """Append-only entries grouped by stream, with sequence checks."""

    def __init__(self, stream_of: Callable[[E], Hashable]) -> None:
        self._stream_of = stream_of
        self._ids: set[Hashable] = set()
        self.streams: dict[Hashable, list[E]] = {}

    def append(self, entry: E, entry_id: Hashable, sequence: int) -> None:
        if entry_id in self._ids:
            raise AlreadyExists(f"Entry {entry_id} already exists.")
        stream = self.streams.setdefault(self._stream_of(entry), [])
        if sequence != len(stream) + 1:
            raise ConflictError("Someone else recorded a change first. Reload and try again.")
        stream.append(entry)
        self._ids.add(entry_id)

    def get(self, stream_id: Hashable) -> list[E]:
        return list(self.streams.get(stream_id, []))


class MemoryUsers:
    def __init__(self) -> None:
        self._t: _Table[User] = _Table(
            "user",
            {
                "username": lambda u: u.username,
                "employee_id": lambda u: u.employee_id,
                "email": lambda u: u.email,
            },
        )

    def get(self, user_id: UserId) -> User | None:
        return self._t.rows.get(user_id)

    def find_by_username(self, username: str) -> User | None:
        return self._t.find("username", username.strip().lower())

    def find_by_employee_id(self, employee_id: str) -> User | None:
        return self._t.find("employee_id", employee_id.strip().upper())

    def find_by_email(self, email: str) -> User | None:
        return self._t.find("email", email.strip().lower())

    def list(self, *, include_deleted: bool = False) -> list[User]:
        users = [u for u in self._t.rows.values() if include_deleted or not u.is_deleted]
        return sorted(users, key=lambda u: u.username)

    def count_active_admins(self) -> int:
        return sum(1 for u in self._t.rows.values() if u.is_active_admin)

    def add(self, user: User) -> None:
        self._t.add(user)

    def update(self, user: User) -> None:
        self._t.update(user)


class MemoryItemTypes:
    def __init__(self) -> None:
        self._t: _Table[ItemType] = _Table("item type", {"code": lambda t: t.code})

    def get(self, item_type_id: ItemTypeId) -> ItemType | None:
        return self._t.rows.get(item_type_id)

    def find_by_code(self, code: str) -> ItemType | None:
        return self._t.find("code", code.strip().upper())

    def list(self, *, include_inactive: bool = False) -> list[ItemType]:
        types = [t for t in self._t.rows.values() if include_inactive or t.is_active]
        return sorted(types, key=lambda t: t.name)

    def add(self, item_type: ItemType) -> None:
        self._t.add(item_type)

    def update(self, item_type: ItemType) -> None:
        self._t.update(item_type)


class MemoryAssets:
    def __init__(self) -> None:
        self._t: _Table[Asset] = _Table(
            "asset",
            {
                "asset_tag": lambda a: a.asset_tag,
                "serial_number": lambda a: (
                    (a.item_type_id, a.serial_number) if a.serial_number else None
                ),
            },
        )

    def get(self, asset_id: AssetId) -> Asset | None:
        return self._t.rows.get(asset_id)

    def find_by_tag(self, asset_tag: str) -> Asset | None:
        return self._t.find("asset_tag", asset_tag.strip().upper())

    def find_by_serial(self, item_type_id: ItemTypeId, serial_number: str) -> Asset | None:
        return self._t.find("serial_number", (item_type_id, serial_number.strip().upper()))

    def list(
        self, *, item_type_id: ItemTypeId | None = None, include_deleted: bool = False
    ) -> list[Asset]:
        assets = [
            a
            for a in self._t.rows.values()
            if (include_deleted or not a.is_deleted)
            and (item_type_id is None or a.item_type_id == item_type_id)
        ]
        return sorted(assets, key=lambda a: a.asset_tag)

    def add(self, asset: Asset) -> None:
        self._t.add(asset)

    def update(self, asset: Asset) -> None:
        self._t.update(asset)


class MemoryStatusEvents:
    def __init__(self) -> None:
        self._s: _Stream[StatusEvent] = _Stream(lambda e: e.asset_id)

    def for_asset(self, asset_id: AssetId) -> list[StatusEvent]:
        return self._s.get(asset_id)

    def append(self, event: StatusEvent) -> None:
        self._s.append(event, event.id, event.sequence)


class MemoryUsage:
    def __init__(self) -> None:
        self._s: _Stream[UsageEntry] = _Stream(lambda e: e.asset_id)

    def for_asset(self, asset_id: AssetId) -> list[UsageEntry]:
        return self._s.get(asset_id)

    def append(self, entry: UsageEntry) -> None:
        if entry.reverses is not None and any(
            e.reverses == entry.reverses for e in self._s.get(entry.asset_id)
        ):
            raise ConflictError("This entry has already been reversed.")
        self._s.append(entry, entry.id, entry.sequence)


class MemoryStock:
    def __init__(self) -> None:
        self._s: _Stream[StockMovement] = _Stream(lambda m: m.item_type_id)

    def for_item_type(self, item_type_id: ItemTypeId) -> list[StockMovement]:
        return self._s.get(item_type_id)

    def append(self, movement: StockMovement) -> None:
        self._s.append(movement, movement.id, movement.sequence)


class MemoryAudit:
    def __init__(self) -> None:
        self._entries: dict[Hashable, AuditEntry] = {}

    def append(self, entry: AuditEntry) -> None:
        if entry.id in self._entries:
            raise AlreadyExists(f"Audit entry {entry.id} already exists.")
        self._entries[entry.id] = entry

    def for_entity(self, entity: str, entity_id: str) -> list[AuditEntry]:
        found = [
            e for e in self._entries.values() if e.entity == entity and e.entity_id == entity_id
        ]
        return sorted(found, key=lambda e: (e.at, e.id))

    def recent(self, limit: int = 100) -> list[AuditEntry]:
        return sorted(self._entries.values(), key=lambda e: (e.at, e.id), reverse=True)[:limit]


class MemoryCommandLog:
    def __init__(self) -> None:
        self._records: dict[CommandId, CommandRecord] = {}

    def get(self, command_id: CommandId) -> CommandRecord | None:
        return self._records.get(command_id)

    def record(self, record: CommandRecord) -> None:
        if record.command_id in self._records:
            raise AlreadyExists(f"Command {record.command_id} was already recorded.")
        self._records[record.command_id] = record


def memory_storage() -> Storage:
    return Storage(
        users=MemoryUsers(),
        item_types=MemoryItemTypes(),
        assets=MemoryAssets(),
        status_events=MemoryStatusEvents(),
        usage=MemoryUsage(),
        stock=MemoryStock(),
        audit=MemoryAudit(),
        commands=MemoryCommandLog(),
    )
