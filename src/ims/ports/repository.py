"""Storage ports (ADR-0002).

Rules every adapter must follow (verified by ``tests/contract``):

* ``add`` stores a new record. Same ID already stored → :class:`AlreadyExists`.
  A unique value (username, email, employee ID, item code, asset tag, serial number
  per item type) already used → :class:`ConflictError`.
* ``update`` takes the record *with its new version*. It succeeds only if the stored
  version is exactly one lower; otherwise :class:`ConflictError` (someone else saved
  first). Unknown ID → :class:`NotFound`.
* Ledgers are append-only. ``append`` succeeds only if the entry's ``sequence`` is the
  next number for its stream; otherwise :class:`ConflictError`. Entries come back in
  sequence order.
* Every single call is atomic on its own; no call spans several records, so
  application code must never assume multi-record transactions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import ItemType
from ims.domain.assets.status import StatusEvent
from ims.domain.audit import AuditEntry
from ims.domain.common.ids import AssetId, CommandId, ItemTypeId, UserId
from ims.domain.common.model import UtcDateTime, ValueModel
from ims.domain.identity.user import User
from ims.domain.stock.ledger import StockMovement
from ims.domain.usage.ledger import UsageEntry


class UserRepository(Protocol):
    def get(self, user_id: UserId) -> User | None: ...
    def find_by_username(self, username: str) -> User | None: ...
    def find_by_employee_id(self, employee_id: str) -> User | None: ...
    def find_by_email(self, email: str) -> User | None: ...
    def list(self, *, include_deleted: bool = False) -> list[User]: ...
    def count_active_admins(self) -> int: ...
    def add(self, user: User) -> None: ...
    def update(self, user: User) -> None: ...


class ItemTypeRepository(Protocol):
    def get(self, item_type_id: ItemTypeId) -> ItemType | None: ...
    def find_by_code(self, code: str) -> ItemType | None: ...
    def list(self, *, include_inactive: bool = False) -> list[ItemType]: ...
    def add(self, item_type: ItemType) -> None: ...
    def update(self, item_type: ItemType) -> None: ...


class AssetRepository(Protocol):
    def get(self, asset_id: AssetId) -> Asset | None: ...
    def find_by_tag(self, asset_tag: str) -> Asset | None: ...
    def find_by_serial(self, item_type_id: ItemTypeId, serial_number: str) -> Asset | None: ...
    def list(
        self, *, item_type_id: ItemTypeId | None = None, include_deleted: bool = False
    ) -> list[Asset]: ...
    def add(self, asset: Asset) -> None: ...
    def update(self, asset: Asset) -> None: ...


class StatusEventRepository(Protocol):
    def for_asset(self, asset_id: AssetId) -> list[StatusEvent]: ...
    def append(self, event: StatusEvent) -> None: ...


class UsageRepository(Protocol):
    def for_asset(self, asset_id: AssetId) -> list[UsageEntry]: ...
    def append(self, entry: UsageEntry) -> None: ...


class StockRepository(Protocol):
    def for_item_type(self, item_type_id: ItemTypeId) -> list[StockMovement]: ...
    def append(self, movement: StockMovement) -> None: ...


class AuditRepository(Protocol):
    def append(self, entry: AuditEntry) -> None: ...
    def for_entity(self, entity: str, entity_id: str) -> list[AuditEntry]: ...
    def recent(self, limit: int = 100) -> list[AuditEntry]: ...


class CommandRecord(ValueModel):
    """Proof that a command finished; replaying the same command ID returns ``result_id``."""

    command_id: CommandId
    action: str
    actor_id: UserId | None
    completed_at: UtcDateTime
    result_id: str


class CommandLog(Protocol):
    def get(self, command_id: CommandId) -> CommandRecord | None: ...
    def record(self, record: CommandRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class Storage:
    """Everything the application layer needs from a backend."""

    users: UserRepository
    item_types: ItemTypeRepository
    assets: AssetRepository
    status_events: StatusEventRepository
    usage: UsageRepository
    stock: StockRepository
    audit: AuditRepository
    commands: CommandLog
