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

from ims.adapters.local_auth import Credential
from ims.adapters.sqlite import schema as s
from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import ItemType, Meter
from ims.domain.assets.configuration import ConfigEvent
from ims.domain.assets.documents import AssetDocument
from ims.domain.assets.firmware import FirmwareRecord
from ims.domain.assets.status import AssetStatus, StatusEvent
from ims.domain.audit import AuditEntry
from ims.domain.common.errors import AlreadyExists, ConflictError, NotFound
from ims.domain.common.ids import (
    AssetId,
    CommandId,
    DefectId,
    DeploymentId,
    DocumentId,
    ItemTypeId,
    KitId,
    KitTemplateId,
    LocationId,
    MaintenanceTaskId,
    ProjectId,
    ReservationId,
    SortieId,
    SurveySessionId,
    UserId,
    WorkOrderId,
)
from ims.domain.identity.roles import Role
from ims.domain.identity.user import PilotLicence, User
from ims.domain.kits import Kit, KitTemplate
from ims.domain.maintenance.defects import Defect
from ims.domain.maintenance.programme import MaintenanceTask, TaskCompletion
from ims.domain.maintenance.work_orders import WorkOrder
from ims.domain.operations.deployment import Deployment
from ims.domain.operations.field_logs import Sortie, SurveySession
from ims.domain.operations.project import Project
from ims.domain.operations.reservation import BookingEvent, Reservation
from ims.domain.sites.site import Site, SiteKind, SiteStatus
from ims.domain.stock.ledger import StockMovement
from ims.domain.stock.reorder import ReorderLevel
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
        "licence_document": u.licence.document if u.licence else None,
        "profile_picture": u.profile_picture,
        "is_active": u.is_active,
        "must_change_password": u.must_change_password,
        "deleted_at": _ts(u.deleted_at),
    }


def _user(r: Row[Any]) -> User:
    licence = (
        PilotLicence(
            number=r.licence_number,
            expires_on=date.fromisoformat(r.licence_expires_on),
            document=r.licence_document,
        )
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


# ------------------------------------------------------------------ sites


def _dec(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _parse_dec(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _site_row(s: Site) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "version": s.version,
        "code": s.code,
        "name": s.name,
        "kind": s.kind.value,
        "region": s.region,
        "latitude": _dec(s.latitude),
        "longitude": _dec(s.longitude),
        "area_hectares": _dec(s.area_hectares),
        "mineral": s.mineral,
        "status": s.status.value,
        "notes": s.notes,
        "deleted_at": _ts(s.deleted_at),
    }


def _site(r: Row[Any]) -> Site:
    return Site(
        id=LocationId(uuid.UUID(r.id)),
        version=r.version,
        code=r.code,
        name=r.name,
        kind=SiteKind(r.kind),
        region=r.region,
        latitude=_parse_dec(r.latitude),
        longitude=_parse_dec(r.longitude),
        area_hectares=_parse_dec(r.area_hectares),
        mineral=r.mineral,
        status=SiteStatus(r.status),
        notes=r.notes,
        deleted_at=_parse_ts(r.deleted_at),
    )


class SqliteSites(_Base):
    table, label = s.sites, "site"

    def get(self, site_id: LocationId) -> Site | None:
        return self._one(s.sites.c.id == str(site_id), _site)

    def find_by_code(self, code: str) -> Site | None:
        return self._one(s.sites.c.code == code.strip().upper(), _site)

    def list(self, *, include_deleted: bool = False) -> list[Site]:
        query = select(s.sites).order_by(s.sites.c.code)
        if not include_deleted:
            query = query.where(s.sites.c.deleted_at.is_(None))
        return self._many(query, _site)

    def add(self, site: Site) -> None:
        self._insert(_site_row(site))

    def update(self, site: Site) -> None:
        self._update_versioned(_site_row(site))


class SqliteCredentialStore:
    """Credential rows for :class:`ims.adapters.local_auth.LocalAuthProvider`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, user_id: UserId) -> Credential | None:
        t = s.local_credentials
        with self._engine.connect() as conn:
            r = conn.execute(select(t).where(t.c.user_id == str(user_id))).first()
        if r is None:
            return None
        return Credential(
            user_id=UserId(uuid.UUID(r.user_id)),
            password_hash=r.password_hash,
            failed_attempts=r.failed_attempts,
            locked_until=_parse_ts(r.locked_until),
            changed_at=_parse_ts(r.changed_at),
        )

    def put(self, credential: Credential) -> None:
        t = s.local_credentials
        row = {
            "user_id": str(credential.user_id),
            "password_hash": credential.password_hash,
            "failed_attempts": credential.failed_attempts,
            "locked_until": _ts(credential.locked_until),
            "changed_at": _ts(credential.changed_at),
        }
        with self._engine.begin() as conn:
            exists = conn.execute(select(t.c.user_id).where(t.c.user_id == row["user_id"])).first()
            if exists is None:
                conn.execute(insert(t).values(**row))
            else:
                conn.execute(update(t).where(t.c.user_id == row["user_id"]).values(**row))


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
        "home_site_id": _id(a.home_site_id),
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
        home_site_id=None if r.home_site_id is None else LocationId(uuid.UUID(r.home_site_id)),
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


# ------------------------------------------------------------------ configuration & documents


def _config_row(e: ConfigEvent) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "component_id": str(e.component_id),
        "sequence": e.sequence,
        "change": e.change.value,
        "parent_id": str(e.parent_id),
        "position": e.position,
        "recorded_at": _ts(e.recorded_at),
        "recorded_by": str(e.recorded_by),
        "command_id": str(e.command_id),
        "note": e.note,
    }


def _config(r: Row[Any]) -> ConfigEvent:
    data = dict(r._mapping)
    data["recorded_at"] = _parse_ts(r.recorded_at)
    return ConfigEvent.model_validate(data)


class SqliteConfiguration(_Base):
    table, label = s.configuration_events, "configuration event"

    def for_component(self, component_id: AssetId) -> list[ConfigEvent]:
        t = s.configuration_events
        return self._many(
            select(t).where(t.c.component_id == str(component_id)).order_by(t.c.sequence), _config
        )

    def for_parent(self, parent_id: AssetId) -> list[ConfigEvent]:
        t = s.configuration_events
        query = (
            select(t)
            .where(t.c.parent_id == str(parent_id))
            .order_by(t.c.recorded_at, t.c.component_id, t.c.sequence)
        )
        return self._many(query, _config)

    def append(self, event: ConfigEvent) -> None:
        self._append_sequenced(_config_row(event), "component_id")


def _document_row(d: AssetDocument) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "version": d.version,
        "asset_id": str(d.asset_id),
        "kind": d.kind.value,
        "reference": d.reference,
        "issuer": d.issuer,
        "issued_on": _d(d.issued_on),
        "valid_until": _d(d.valid_until),
        "file": d.file,
        "notes": d.notes,
        "deleted_at": _ts(d.deleted_at),
    }


def _document(r: Row[Any]) -> AssetDocument:
    data = dict(r._mapping)
    data["deleted_at"] = _parse_ts(r.deleted_at)
    return AssetDocument.model_validate(data)


class SqliteDocuments(_Base):
    table, label = s.asset_documents, "document"

    def get(self, document_id: DocumentId) -> AssetDocument | None:
        return self._one(s.asset_documents.c.id == str(document_id), _document)

    def for_asset(self, asset_id: AssetId, *, include_deleted: bool = False) -> list[AssetDocument]:
        t = s.asset_documents
        query = select(t).where(t.c.asset_id == str(asset_id)).order_by(t.c.kind, t.c.id)
        if not include_deleted:
            query = query.where(t.c.deleted_at.is_(None))
        return self._many(query, _document)

    def list(self) -> list[AssetDocument]:
        t = s.asset_documents
        query = select(t).where(t.c.deleted_at.is_(None)).order_by(t.c.asset_id, t.c.kind, t.c.id)
        return self._many(query, _document)

    def add(self, document: AssetDocument) -> None:
        self._insert(_document_row(document))

    def update(self, document: AssetDocument) -> None:
        self._update_versioned(_document_row(document))


def _firmware_row(f: FirmwareRecord) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "asset_id": str(f.asset_id),
        "sequence": f.sequence,
        "version": f.version,
        "installed_on": _d(f.installed_on),
        "recorded_at": _ts(f.recorded_at),
        "recorded_by": str(f.recorded_by),
        "command_id": str(f.command_id),
        "note": f.note,
    }


def _firmware(r: Row[Any]) -> FirmwareRecord:
    data = dict(r._mapping)
    data["recorded_at"] = _parse_ts(r.recorded_at)
    return FirmwareRecord.model_validate(data)


class SqliteFirmware(_Base):
    table, label = s.firmware_records, "firmware record"

    def for_asset(self, asset_id: AssetId) -> list[FirmwareRecord]:
        t = s.firmware_records
        return self._many(
            select(t).where(t.c.asset_id == str(asset_id)).order_by(t.c.sequence), _firmware
        )

    def append(self, record: FirmwareRecord) -> None:
        self._append_sequenced(_firmware_row(record), "asset_id")


# ------------------------------------------------------------------ kits & reorder levels


def _template_row(t: KitTemplate) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "version": t.version,
        "name": t.name,
        "name_key": t.name.lower(),
        "discipline": t.discipline.value,
        "lines": json.dumps(
            [
                {"item_type_id": str(line.item_type_id), "quantity": line.quantity}
                for line in t.lines
            ]
        ),
        "notes": t.notes,
        "is_active": t.is_active,
    }


def _template(r: Row[Any]) -> KitTemplate:
    data = dict(r._mapping)
    data.pop("name_key")
    data["lines"] = tuple(json.loads(r.lines))
    return KitTemplate.model_validate(data)


class SqliteKitTemplates(_Base):
    table, label = s.kit_templates, "kit template"

    def get(self, template_id: KitTemplateId) -> KitTemplate | None:
        return self._one(s.kit_templates.c.id == str(template_id), _template)

    def list(self, *, include_inactive: bool = False) -> list[KitTemplate]:
        t = s.kit_templates
        query = select(t).order_by(t.c.name)
        if not include_inactive:
            query = query.where(t.c.is_active.is_(True))
        return self._many(query, _template)

    def add(self, template: KitTemplate) -> None:
        self._insert(_template_row(template))

    def update(self, template: KitTemplate) -> None:
        self._update_versioned(_template_row(template))


def _kit_row(k: Kit) -> dict[str, Any]:
    return {
        "id": str(k.id),
        "version": k.version,
        "code": k.code,
        "name": k.name,
        "template_id": _id(k.template_id),
        "members": json.dumps([str(m) for m in k.members]),
        "home_site_id": _id(k.home_site_id),
        "notes": k.notes,
        "deleted_at": _ts(k.deleted_at),
    }


def _kit(r: Row[Any]) -> Kit:
    data = dict(r._mapping)
    data["members"] = tuple(json.loads(r.members))
    data["deleted_at"] = _parse_ts(r.deleted_at)
    return Kit.model_validate(data)


class SqliteKits(_Base):
    table, label = s.kits, "kit"

    def get(self, kit_id: KitId) -> Kit | None:
        return self._one(s.kits.c.id == str(kit_id), _kit)

    def find_by_code(self, code: str) -> Kit | None:
        normalised = code.strip().upper()
        if not normalised.startswith("KIT-"):
            normalised = f"KIT-{normalised}"
        return self._one(s.kits.c.code == normalised, _kit)

    def find_by_member(self, asset_id: AssetId) -> Kit | None:
        # Kits are few; membership is stored as a list, as it will be on SharePoint.
        return next((k for k in self.list() if asset_id in k.members), None)

    def list(self, *, include_deleted: bool = False) -> list[Kit]:
        query = select(s.kits).order_by(s.kits.c.code)
        if not include_deleted:
            query = query.where(s.kits.c.deleted_at.is_(None))
        return self._many(query, _kit)

    def add(self, kit: Kit) -> None:
        self._insert(_kit_row(kit))

    def update(self, kit: Kit) -> None:
        self._update_versioned(_kit_row(kit))


def _reorder_row(level: ReorderLevel) -> dict[str, Any]:
    return {
        "id": str(level.id),
        "version": level.version,
        "item_type_id": str(level.item_type_id),
        "location_id": str(level.location_id),
        "level": level.level,
    }


class SqliteReorderLevels(_Base):
    table, label = s.reorder_levels, "reorder level"

    def get(self, level_id: uuid.UUID) -> ReorderLevel | None:
        return self._one(
            s.reorder_levels.c.id == str(level_id),
            lambda r: ReorderLevel.model_validate(dict(r._mapping)),
        )

    def list(self) -> list[ReorderLevel]:
        t = s.reorder_levels
        return self._many(
            select(t).order_by(t.c.item_type_id, t.c.location_id),
            lambda r: ReorderLevel.model_validate(dict(r._mapping)),
        )

    def add(self, level: ReorderLevel) -> None:
        self._insert(_reorder_row(level))

    def update(self, level: ReorderLevel) -> None:
        self._update_versioned(_reorder_row(level))


# ------------------------------------------------------------------ operations
#
# Operations records map field-for-field onto their tables; list-valued fields are stored
# as JSON text (SharePoint will hold them in multi-line text columns the same way).


def _record_row(record: Any, json_fields: frozenset[str]) -> dict[str, Any]:
    row: dict[str, Any] = record.model_dump(mode="json")
    for name in json_fields:
        row[name] = json.dumps(row[name])
    return row


def _record_of[T](model: type[T], json_fields: frozenset[str]) -> Callable[[Row[Any]], T]:
    def read(r: Row[Any]) -> T:
        data = dict(r._mapping)
        for name in json_fields:
            data[name] = json.loads(data[name])
        return model.model_validate(data)  # type: ignore[attr-defined, no-any-return]

    return read


_DEPLOYMENT_JSON = frozenset({"asset_ids", "kit_ids", "crew_ids", "returns"})
_SORTIE_JSON = frozenset({"battery_ids", "media_ids", "usage_entries"})
_SESSION_JSON = frozenset({"rover_ids", "battery_ids", "usage_entries"})


class SqliteProjects(_Base):
    table, label = s.projects, "project"
    _read = staticmethod(_record_of(Project, frozenset()))

    def get(self, project_id: ProjectId) -> Project | None:
        return self._one(s.projects.c.id == str(project_id), self._read)

    def find_by_code(self, code: str) -> Project | None:
        normalised = code.strip().upper().replace(" ", "-")
        if not normalised.startswith("PRJ-"):
            normalised = f"PRJ-{normalised}"
        return self._one(s.projects.c.code == normalised, self._read)

    def list(self, *, include_deleted: bool = False) -> list[Project]:
        t = s.projects
        query = select(t).order_by(t.c.starts_on.desc(), t.c.code.desc())
        if not include_deleted:
            query = query.where(t.c.deleted_at.is_(None))
        return self._many(query, self._read)

    def add(self, project: Project) -> None:
        self._insert(_record_row(project, frozenset()))

    def update(self, project: Project) -> None:
        self._update_versioned(_record_row(project, frozenset()))


class SqliteDeployments(_Base):
    table, label = s.deployments, "deployment"
    _read = staticmethod(_record_of(Deployment, _DEPLOYMENT_JSON))

    def get(self, deployment_id: DeploymentId) -> Deployment | None:
        return self._one(s.deployments.c.id == str(deployment_id), self._read)

    def for_project(self, project_id: ProjectId) -> list[Deployment]:
        t = s.deployments
        query = select(t).where(t.c.project_id == str(project_id))
        return self._many(query.order_by(t.c.created_at, t.c.id), self._read)

    def list(self) -> list[Deployment]:
        t = s.deployments
        return self._many(select(t).order_by(t.c.created_at.desc(), t.c.id.desc()), self._read)

    def add(self, deployment: Deployment) -> None:
        self._insert(_record_row(deployment, _DEPLOYMENT_JSON))

    def update(self, deployment: Deployment) -> None:
        self._update_versioned(_record_row(deployment, _DEPLOYMENT_JSON))


class SqliteSorties(_Base):
    table, label = s.sorties, "flight log"
    _read = staticmethod(_record_of(Sortie, _SORTIE_JSON))

    def get(self, sortie_id: SortieId) -> Sortie | None:
        return self._one(s.sorties.c.id == str(sortie_id), self._read)

    def for_project(self, project_id: ProjectId) -> list[Sortie]:
        t = s.sorties
        query = select(t).where(t.c.project_id == str(project_id))
        return self._many(query.order_by(t.c.flown_on, t.c.recorded_at, t.c.id), self._read)

    def list(self) -> list[Sortie]:
        t = s.sorties
        return self._many(select(t).order_by(t.c.flown_on, t.c.recorded_at, t.c.id), self._read)

    def add(self, sortie: Sortie) -> None:
        self._insert(_record_row(sortie, _SORTIE_JSON))

    def update(self, sortie: Sortie) -> None:
        self._update_versioned(_record_row(sortie, _SORTIE_JSON))


class SqliteSurveySessions(_Base):
    table, label = s.survey_sessions, "survey session"
    _read = staticmethod(_record_of(SurveySession, _SESSION_JSON))

    def get(self, session_id: SurveySessionId) -> SurveySession | None:
        return self._one(s.survey_sessions.c.id == str(session_id), self._read)

    def for_project(self, project_id: ProjectId) -> list[SurveySession]:
        t = s.survey_sessions
        query = select(t).where(t.c.project_id == str(project_id))
        return self._many(query.order_by(t.c.surveyed_on, t.c.recorded_at, t.c.id), self._read)

    def list(self) -> list[SurveySession]:
        t = s.survey_sessions
        query = select(t).order_by(t.c.surveyed_on, t.c.recorded_at, t.c.id)
        return self._many(query, self._read)

    def add(self, session: SurveySession) -> None:
        self._insert(_record_row(session, _SESSION_JSON))

    def update(self, session: SurveySession) -> None:
        self._update_versioned(_record_row(session, _SESSION_JSON))


_RESERVATION_JSON = frozenset({"asset_ids", "kit_ids"})


class SqliteReservations(_Base):
    table, label = s.reservations, "reservation"
    _read = staticmethod(_record_of(Reservation, _RESERVATION_JSON))

    def get(self, reservation_id: ReservationId) -> Reservation | None:
        return self._one(s.reservations.c.id == str(reservation_id), self._read)

    def for_project(self, project_id: ProjectId) -> list[Reservation]:
        t = s.reservations
        query = select(t).where(t.c.project_id == str(project_id))
        return self._many(query.order_by(t.c.starts_on, t.c.requested_at, t.c.id), self._read)

    def list(self) -> list[Reservation]:
        t = s.reservations
        return self._many(select(t).order_by(t.c.starts_on, t.c.requested_at, t.c.id), self._read)

    def add(self, reservation: Reservation) -> None:
        self._insert(_record_row(reservation, _RESERVATION_JSON))

    def update(self, reservation: Reservation) -> None:
        self._update_versioned(_record_row(reservation, _RESERVATION_JSON))


class SqliteBookings(_Base):
    table, label = s.booking_events, "booking"
    _read = staticmethod(_record_of(BookingEvent, frozenset()))

    def for_asset(self, asset_id: AssetId) -> list[BookingEvent]:
        t = s.booking_events
        return self._many(
            select(t).where(t.c.asset_id == str(asset_id)).order_by(t.c.sequence), self._read
        )

    def append(self, event: BookingEvent) -> None:
        self._append_sequenced(_record_row(event, frozenset()), "asset_id")


# ------------------------------------------------------------------ maintenance


class SqliteMaintenanceTasks(_Base):
    table, label = s.maintenance_tasks, "maintenance task"
    _read = staticmethod(_record_of(MaintenanceTask, frozenset()))

    def get(self, task_id: MaintenanceTaskId) -> MaintenanceTask | None:
        return self._one(s.maintenance_tasks.c.id == str(task_id), self._read)

    def list(self, *, include_inactive: bool = False) -> list[MaintenanceTask]:
        t = s.maintenance_tasks
        query = select(t).order_by(t.c.item_type_id, t.c.name, t.c.id)
        if not include_inactive:
            query = query.where(t.c.is_active.is_(True))
        return self._many(query, self._read)

    def add(self, task: MaintenanceTask) -> None:
        self._insert(_record_row(task, frozenset()))

    def update(self, task: MaintenanceTask) -> None:
        self._update_versioned(_record_row(task, frozenset()))


class SqliteCompletions(_Base):
    table, label = s.task_completions, "maintenance record"
    _read = staticmethod(_record_of(TaskCompletion, frozenset({"meters"})))

    def for_asset(self, asset_id: AssetId) -> list[TaskCompletion]:
        t = s.task_completions
        return self._many(
            select(t).where(t.c.asset_id == str(asset_id)).order_by(t.c.sequence), self._read
        )

    def append(self, completion: TaskCompletion) -> None:
        self._append_sequenced(_record_row(completion, frozenset({"meters"})), "asset_id")


_WORK_ORDER_JSON = frozenset({"task_ids", "defect_ids"})


class SqliteDefects(_Base):
    table, label = s.defects, "defect"
    _read = staticmethod(_record_of(Defect, frozenset()))

    def get(self, defect_id: DefectId) -> Defect | None:
        return self._one(s.defects.c.id == str(defect_id), self._read)

    def for_asset(self, asset_id: AssetId) -> list[Defect]:
        t = s.defects
        query = select(t).where(t.c.asset_id == str(asset_id))
        return self._many(query.order_by(t.c.reported_at.desc(), t.c.number.desc()), self._read)

    def list(self) -> list[Defect]:
        t = s.defects
        return self._many(select(t).order_by(t.c.reported_at.desc(), t.c.number.desc()), self._read)

    def add(self, defect: Defect) -> None:
        self._insert(_record_row(defect, frozenset()))

    def update(self, defect: Defect) -> None:
        self._update_versioned(_record_row(defect, frozenset()))


class SqliteWorkOrders(_Base):
    table, label = s.work_orders, "work order"
    _read = staticmethod(_record_of(WorkOrder, _WORK_ORDER_JSON))

    def get(self, work_order_id: WorkOrderId) -> WorkOrder | None:
        return self._one(s.work_orders.c.id == str(work_order_id), self._read)

    def for_asset(self, asset_id: AssetId) -> list[WorkOrder]:
        t = s.work_orders
        query = select(t).where(t.c.asset_id == str(asset_id))
        return self._many(query.order_by(t.c.opened_at.desc(), t.c.number.desc()), self._read)

    def list(self) -> list[WorkOrder]:
        t = s.work_orders
        return self._many(select(t).order_by(t.c.opened_at.desc(), t.c.number.desc()), self._read)

    def add(self, order: WorkOrder) -> None:
        self._insert(_record_row(order, _WORK_ORDER_JSON))

    def update(self, order: WorkOrder) -> None:
        self._update_versioned(_record_row(order, _WORK_ORDER_JSON))


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
        sites=SqliteSites(engine),
        item_types=SqliteItemTypes(engine),
        assets=SqliteAssets(engine),
        status_events=SqliteStatusEvents(engine),
        usage=SqliteUsage(engine),
        stock=SqliteStock(engine),
        configuration=SqliteConfiguration(engine),
        documents=SqliteDocuments(engine),
        firmware=SqliteFirmware(engine),
        kit_templates=SqliteKitTemplates(engine),
        kits=SqliteKits(engine),
        reorder_levels=SqliteReorderLevels(engine),
        projects=SqliteProjects(engine),
        deployments=SqliteDeployments(engine),
        sorties=SqliteSorties(engine),
        survey_sessions=SqliteSurveySessions(engine),
        reservations=SqliteReservations(engine),
        bookings=SqliteBookings(engine),
        maintenance_tasks=SqliteMaintenanceTasks(engine),
        completions=SqliteCompletions(engine),
        defects=SqliteDefects(engine),
        work_orders=SqliteWorkOrders(engine),
        audit=SqliteAudit(engine),
        commands=SqliteCommandLog(engine),
    )
