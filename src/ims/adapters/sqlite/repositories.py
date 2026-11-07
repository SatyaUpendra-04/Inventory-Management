"""SQLite implementations of the storage ports."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, Row, Table, and_, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from ims.adapters.sqlite import schema as s
from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import ItemType, Meter
from ims.domain.assets.status import AssetStatus, StatusEvent
from ims.domain.audit import AuditEntry
from ims.domain.common.errors import AlreadyExists, ConflictError, NotFound
from ims.domain.common.ids import AssetId, CommandId, ItemTypeId, UserId
from ims.domain.identity.roles import Role
from ims.domain.identity.user import PilotLicence, User
from ims.domain.stock.ledger import StockMovement
from ims.domain.usage.ledger import UsageEntry
from ims.ports.repository import CommandRecord, Storage

# ------------------------------------------------------------------ value conversion


def _ts(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_ts(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _d(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _parse_d(value: str | None) -> date | None:
    return None if value is None else date.fromisoformat(value)


def _id(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)


def _parse_id(value: str | None) -> uuid.UUID | None:
    return None if value is None else uuid.UUID(value)


# ------------------------------------------------------------------ shared behaviour


def _unique_column(error: IntegrityError, table: Table) -> str:
    """Best-effort name of the unique column that rejected a write (for the message)."""
    message = str(error.orig)
    prefix = f"{table.name}."
    columns = [part.strip().removeprefix(prefix) for part in message.split(":")[-1].split(",")]
    return ", ".join(c.replace("_", " ") for c in columns if c)


class _Base:
    table: Table
    label: str

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _insert(self, row: Mapping[str, Any], key: str = "id") -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(insert(self.table).values(**row))
        except IntegrityError as exc:
            with self._engine.connect() as conn:
                exists = conn.execute(
                    select(self.table.c[key]).where(self.table.c[key] == row[key])
                ).first()
            if exists is not None:
                raise AlreadyExists(f"{self.label} {row[key]} already exists.") from exc
            raise ConflictError(f"{_unique_column(exc, self.table)} is already in use.") from exc

    def _update_versioned(self, row: Mapping[str, Any]) -> None:
        t = self.table
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    update(t)
                    .where(and_(t.c.id == row["id"], t.c.version == row["version"] - 1))
                    .values(**row)
                )
                changed = result.rowcount
        except IntegrityError as exc:
            raise ConflictError(f"{_unique_column(exc, t)} is already in use.") from exc
        if changed == 1:
            return
        with self._engine.connect() as conn:
            exists = conn.execute(select(t.c.id).where(t.c.id == row["id"])).first()
        if exists is None:
            raise NotFound(f"{self.label} {row['id']} does not exist.")
        raise ConflictError(f"This {self.label} was changed by someone else. Reload and try again.")

    def _append_sequenced(self, row: Mapping[str, Any], stream_column: str) -> None:
        """Appends a ledger row; the (stream, sequence) unique constraint guards ordering."""
        t = self.table
        with self._engine.connect() as conn:
            if conn.execute(select(t.c.id).where(t.c.id == row["id"])).first() is not None:
                raise AlreadyExists(f"Entry {row['id']} already exists.")
            count = conn.execute(
                select(func.count()).where(t.c[stream_column] == row[stream_column])
            ).scalar_one()
        if row["sequence"] != count + 1:
            raise ConflictError("Someone else recorded a change first. Reload and try again.")
        try:
            with self._engine.begin() as conn:
                conn.execute(insert(t).values(**row))
        except IntegrityError as exc:
            raise ConflictError(
                "Someone else recorded a change first. Reload and try again."
            ) from exc

    def _one[T](self, where: Any, mapper: Callable[[Row[Any]], T]) -> T | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(self.table).where(where)).first()
        return None if row is None else mapper(row)

    def _many[T](self, query: Any, mapper: Callable[[Row[Any]], T]) -> list[T]:
        with self._engine.connect() as conn:
            return [mapper(row) for row in conn.execute(query)]


# ------------------------------------------------------------------ users


def _user_row(u: User) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "version": u.version,
        "username": u.username,
        "full_name": u.full_name,
        "role": u.role.value,
        "employee_id": u.employee_id,
        "email": u.email,
        "phone": u.phone,
        "licence_number": u.licence.number if u.licence else None,
        "licence_expires_on": _d(u.licence.expires_on) if u.licence else None,
        "profile_picture": u.profile_picture,
        "is_active": u.is_active,
        "must_change_password": u.must_change_password,
        "deleted_at": _ts(u.deleted_at),
    }


def _user(r: Row[Any]) -> User:
    licence = (
        PilotLicence(number=r.licence_number, expires_on=date.fromisoformat(r.licence_expires_on))
        if r.licence_number
        else None
    )
    return User(
        id=UserId(uuid.UUID(r.id)),
        version=r.version,
        username=r.username,
        full_name=r.full_name,
        role=Role(r.role),
        employee_id=r.employee_id,
        email=r.email,
        phone=r.phone,
        licence=licence,
        profile_picture=r.profile_picture,
        is_active=r.is_active,
        must_change_password=r.must_change_password,
        deleted_at=_parse_ts(r.deleted_at),
    )


class SqliteUsers(_Base):
    table, label = s.users, "user"

    def get(self, user_id: UserId) -> User | None:
        return self._one(s.users.c.id == str(user_id), _user)

    def find_by_username(self, username: str) -> User | None:
        return self._one(s.users.c.username == username.strip().lower(), _user)

    def find_by_employee_id(self, employee_id: str) -> User | None:
        return self._one(s.users.c.employee_id == employee_id.strip().upper(), _user)

    def find_by_email(self, email: str) -> User | None:
        return self._one(s.users.c.email == email.strip().lower(), _user)

    def list(self, *, include_deleted: bool = False) -> list[User]:
        query = select(s.users).order_by(s.users.c.username)
        if not include_deleted:
            query = query.where(s.users.c.deleted_at.is_(None))
        return self._many(query, _user)

    def count_active_admins(self) -> int:
        with self._engine.connect() as conn:
            return conn.execute(
                select(func.count()).where(
                    s.users.c.role == Role.ADMIN.value,
                    s.users.c.is_active.is_(True),
                    s.users.c.deleted_at.is_(None),
                )
            ).scalar_one()

    def add(self, user: User) -> None:
        self._insert(_user_row(user))

    def update(self, user: User) -> None:
        self._update_versioned(_user_row(user))


# ------------------------------------------------------------------ catalogue & assets


def _item_type_row(t: ItemType) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "version": t.version,
        "code": t.code,
        "name": t.name,
        "category": t.category.value,
        "discipline": t.discipline.value,
        "tracking": t.tracking.value,
        "meters": ",".join(sorted(m.value for m in t.meters)),
        "is_component": t.is_component,
        "tag_prefix": t.tag_prefix,
        "tracks_warranty": t.tracks_warranty,
        "tracks_calibration": t.tracks_calibration,
        "battery_family": t.battery_family,
        "is_active": t.is_active,
    }


def _item_type(r: Row[Any]) -> ItemType:
    data = dict(r._mapping)
    data["meters"] = frozenset(Meter(m) for m in r.meters.split(",") if m)
    data["id"] = uuid.UUID(r.id)
    return ItemType.model_validate(data)


class SqliteItemTypes(_Base):
    table, label = s.item_types, "item type"

    def get(self, item_type_id: ItemTypeId) -> ItemType | None:
        return self._one(s.item_types.c.id == str(item_type_id), _item_type)

    def find_by_code(self, code: str) -> ItemType | None:
        return self._one(s.item_types.c.code == code.strip().upper(), _item_type)

    def list(self, *, include_inactive: bool = False) -> list[ItemType]:
        query = select(s.item_types).order_by(s.item_types.c.name)
        if not include_inactive:
            query = query.where(s.item_types.c.is_active.is_(True))
        return self._many(query, _item_type)

    def add(self, item_type: ItemType) -> None:
        self._insert(_item_type_row(item_type))

    def update(self, item_type: ItemType) -> None:
        self._update_versioned(_item_type_row(item_type))


def _asset_row(a: Asset) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "version": a.version,
        "item_type_id": str(a.item_type_id),
        "asset_tag": a.asset_tag,
        "serial_number": a.serial_number,
        "make": a.make,
        "model": a.model,
        "acquired_on": _d(a.acquired_on),
        "warranty_until": _d(a.warranty_until),
        "notes": a.notes,
        "deleted_at": _ts(a.deleted_at),
    }


def _asset(r: Row[Any]) -> Asset:
    return Asset(
        id=AssetId(uuid.UUID(r.id)),
        version=r.version,
        item_type_id=ItemTypeId(uuid.UUID(r.item_type_id)),
        asset_tag=r.asset_tag,
        serial_number=r.serial_number,
        make=r.make,
        model=r.model,
        acquired_on=_parse_d(r.acquired_on),
        warranty_until=_parse_d(r.warranty_until),
        notes=r.notes,
        deleted_at=_parse_ts(r.deleted_at),
    )


class SqliteAssets(_Base):
    table, label = s.assets, "asset"

    def get(self, asset_id: AssetId) -> Asset | None:
        return self._one(s.assets.c.id == str(asset_id), _asset)

    def find_by_tag(self, asset_tag: str) -> Asset | None:
        return self._one(s.assets.c.asset_tag == asset_tag.strip().upper(), _asset)

    def find_by_serial(self, item_type_id: ItemTypeId, serial_number: str) -> Asset | None:
        return self._one(
            and_(
                s.assets.c.item_type_id == str(item_type_id),
                s.assets.c.serial_number == serial_number.strip().upper(),
            ),
            _asset,
        )

    def list(
        self, *, item_type_id: ItemTypeId | None = None, include_deleted: bool = False
    ) -> list[Asset]:
        query = select(s.assets).order_by(s.assets.c.asset_tag)
        if item_type_id is not None:
            query = query.where(s.assets.c.item_type_id == str(item_type_id))
        if not include_deleted:
            query = query.where(s.assets.c.deleted_at.is_(None))
        return self._many(query, _asset)

    def add(self, asset: Asset) -> None:
        self._insert(_asset_row(asset))

    def update(self, asset: Asset) -> None:
        self._update_versioned(_asset_row(asset))


# ------------------------------------------------------------------ ledgers


def _status_row(e: StatusEvent) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "asset_id": str(e.asset_id),
        "sequence": e.sequence,
        "command_id": str(e.command_id),
        "recorded_at": _ts(e.recorded_at),
        "recorded_by": str(e.recorded_by),
        "before_serviceability": e.before.serviceability.value,
        "before_custody": e.before.custody.value,
        "after_serviceability": e.after.serviceability.value,
        "after_custody": e.after.custody.value,
        "reason": e.reason,
        "project_id": _id(e.project_id),
    }


def _status(r: Row[Any]) -> StatusEvent:
    return StatusEvent.model_validate(
        {
            "id": r.id,
            "asset_id": r.asset_id,
            "sequence": r.sequence,
            "command_id": r.command_id,
            "recorded_at": _parse_ts(r.recorded_at),
            "recorded_by": r.recorded_by,
            "before": AssetStatus(serviceability=r.before_serviceability, custody=r.before_custody),
            "after": AssetStatus(serviceability=r.after_serviceability, custody=r.after_custody),
            "reason": r.reason,
            "project_id": r.project_id,
        }
    )


class SqliteStatusEvents(_Base):
    table, label = s.status_events, "status event"

    def for_asset(self, asset_id: AssetId) -> list[StatusEvent]:
        t = s.status_events
        return self._many(
            select(t).where(t.c.asset_id == str(asset_id)).order_by(t.c.sequence), _status
        )

    def append(self, event: StatusEvent) -> None:
        self._append_sequenced(_status_row(event), "asset_id")


def _usage_row(e: UsageEntry) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "asset_id": str(e.asset_id),
        "sequence": e.sequence,
        "meter": e.meter.value,
        "amount": str(e.amount),
        "occurred_on": _d(e.occurred_on),
        "source": e.source.value,
        "recorded_at": _ts(e.recorded_at),
        "recorded_by": str(e.recorded_by),
        "command_id": str(e.command_id),
        "project_id": _id(e.project_id),
        "reverses": _id(e.reverses),
        "note": e.note,
    }


def _usage(r: Row[Any]) -> UsageEntry:
    data = dict(r._mapping)
    data["amount"] = Decimal(r.amount)
    data["recorded_at"] = _parse_ts(r.recorded_at)
    return UsageEntry.model_validate(data)


class SqliteUsage(_Base):
    table, label = s.usage_entries, "usage entry"

    def for_asset(self, asset_id: AssetId) -> list[UsageEntry]:
        t = s.usage_entries
        return self._many(
            select(t).where(t.c.asset_id == str(asset_id)).order_by(t.c.sequence), _usage
        )

    def append(self, entry: UsageEntry) -> None:
        if entry.reverses is not None:
            t = s.usage_entries
            reversed_already = self._one(t.c.reverses == str(entry.reverses), _usage)
            if reversed_already is not None:
                raise ConflictError("This entry has already been reversed.")
        self._append_sequenced(_usage_row(entry), "asset_id")


def _stock_row(m: StockMovement) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "item_type_id": str(m.item_type_id),
        "sequence": m.sequence,
        "location_id": str(m.location_id),
        "kind": m.kind.value,
        "quantity": m.quantity,
        "recorded_at": _ts(m.recorded_at),
        "recorded_by": str(m.recorded_by),
        "command_id": str(m.command_id),
        "project_id": _id(m.project_id),
        "reason": m.reason,
    }


def _stock(r: Row[Any]) -> StockMovement:
    data = dict(r._mapping)
    data["recorded_at"] = _parse_ts(r.recorded_at)
    return StockMovement.model_validate(data)


class SqliteStock(_Base):
    table, label = s.stock_movements, "stock movement"

    def for_item_type(self, item_type_id: ItemTypeId) -> list[StockMovement]:
        t = s.stock_movements
        return self._many(
            select(t).where(t.c.item_type_id == str(item_type_id)).order_by(t.c.sequence), _stock
        )

    def append(self, movement: StockMovement) -> None:
        self._append_sequenced(_stock_row(movement), "item_type_id")


# ------------------------------------------------------------------ audit & commands


def _audit_row(e: AuditEntry) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "command_id": str(e.command_id),
        "at": _ts(e.at),
        "actor_id": _id(e.actor_id),
        "action": e.action,
        "entity": e.entity,
        "entity_id": e.entity_id,
        "before_json": None if e.before is None else json.dumps(e.before, sort_keys=True),
        "after_json": None if e.after is None else json.dumps(e.after, sort_keys=True),
    }


def _audit(r: Row[Any]) -> AuditEntry:
    return AuditEntry.model_validate(
        {
            "id": r.id,
            "command_id": r.command_id,
            "at": _parse_ts(r.at),
            "actor_id": r.actor_id,
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "before": None if r.before_json is None else json.loads(r.before_json),
            "after": None if r.after_json is None else json.loads(r.after_json),
        }
    )


class SqliteAudit(_Base):
    table, label = s.audit_log, "audit entry"

    def append(self, entry: AuditEntry) -> None:
        self._insert(_audit_row(entry))

    def for_entity(self, entity: str, entity_id: str) -> list[AuditEntry]:
        t = s.audit_log
        query = (
            select(t)
            .where(t.c.entity == entity, t.c.entity_id == entity_id)
            .order_by(t.c.at, t.c.id)
        )
        return self._many(query, _audit)

    def recent(self, limit: int = 100) -> list[AuditEntry]:
        t = s.audit_log
        return self._many(select(t).order_by(t.c.at.desc(), t.c.id.desc()).limit(limit), _audit)


def _command(r: Row[Any]) -> CommandRecord:
    return CommandRecord(
        command_id=CommandId(uuid.UUID(r.command_id)),
        action=r.action,
        actor_id=None if r.actor_id is None else UserId(uuid.UUID(r.actor_id)),
        completed_at=datetime.fromisoformat(r.completed_at),
        result_id=r.result_id,
    )


class SqliteCommandLog(_Base):
    table, label = s.command_log, "command"

    def get(self, command_id: CommandId) -> CommandRecord | None:
        return self._one(s.command_log.c.command_id == str(command_id), _command)

    def record(self, record: CommandRecord) -> None:
        self._insert(
            {
                "command_id": str(record.command_id),
                "action": record.action,
                "actor_id": _id(record.actor_id),
                "completed_at": _ts(record.completed_at),
                "result_id": record.result_id,
            },
            key="command_id",
        )


def sqlite_storage(engine: Engine) -> Storage:
    return Storage(
        users=SqliteUsers(engine),
        item_types=SqliteItemTypes(engine),
        assets=SqliteAssets(engine),
        status_events=SqliteStatusEvents(engine),
        usage=SqliteUsage(engine),
        stock=SqliteStock(engine),
        audit=SqliteAudit(engine),
        commands=SqliteCommandLog(engine),
    )
