"""In-memory storage: the reference implementation of the storage ports.

Used for fast application tests and as the baseline every other adapter is compared
with in the contract tests. Not for production: nothing is persisted.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Hashable
from typing import Protocol

from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import ItemType
from ims.domain.assets.configuration import ConfigEvent
from ims.domain.assets.documents import AssetDocument
from ims.domain.assets.firmware import FirmwareRecord
from ims.domain.assets.status import StatusEvent
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
from ims.domain.identity.user import User
from ims.domain.kits import Kit, KitTemplate
from ims.domain.maintenance.defects import Defect
from ims.domain.maintenance.programme import MaintenanceTask, TaskCompletion
from ims.domain.maintenance.work_orders import WorkOrder
from ims.domain.operations.deployment import Deployment
from ims.domain.operations.field_logs import Sortie, SurveySession
from ims.domain.operations.project import Project
from ims.domain.operations.reservation import BookingEvent, Reservation
from ims.domain.sites.site import Site
from ims.domain.stock.ledger import StockMovement
from ims.domain.stock.reorder import ReorderLevel
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


class MemorySites:
    def __init__(self) -> None:
        self._t: _Table[Site] = _Table("site", {"code": lambda s: s.code})

    def get(self, site_id: LocationId) -> Site | None:
        return self._t.rows.get(site_id)

    def find_by_code(self, code: str) -> Site | None:
        return self._t.find("code", code.strip().upper())

    def list(self, *, include_deleted: bool = False) -> list[Site]:
        sites = [s for s in self._t.rows.values() if include_deleted or not s.is_deleted]
        return sorted(sites, key=lambda s: s.code)

    def add(self, site: Site) -> None:
        self._t.add(site)

    def update(self, site: Site) -> None:
        self._t.update(site)


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


class MemoryConfiguration:
    def __init__(self) -> None:
        self._s: _Stream[ConfigEvent] = _Stream(lambda e: e.component_id)

    def for_component(self, component_id: AssetId) -> list[ConfigEvent]:
        return self._s.get(component_id)

    def for_parent(self, parent_id: AssetId) -> list[ConfigEvent]:
        events = [
            e for stream in self._s.streams.values() for e in stream if e.parent_id == parent_id
        ]
        return sorted(events, key=lambda e: (e.recorded_at, e.component_id, e.sequence))

    def append(self, event: ConfigEvent) -> None:
        self._s.append(event, event.id, event.sequence)


class MemoryDocuments:
    def __init__(self) -> None:
        self._t: _Table[AssetDocument] = _Table("document", {})

    def get(self, document_id: DocumentId) -> AssetDocument | None:
        return self._t.rows.get(document_id)

    def for_asset(self, asset_id: AssetId, *, include_deleted: bool = False) -> list[AssetDocument]:
        docs = [
            d
            for d in self._t.rows.values()
            if d.asset_id == asset_id and (include_deleted or not d.is_deleted)
        ]
        return sorted(docs, key=lambda d: (d.kind.value, str(d.id)))

    def list(self) -> list[AssetDocument]:
        return sorted(
            (d for d in self._t.rows.values() if not d.is_deleted),
            key=lambda d: (str(d.asset_id), d.kind.value, str(d.id)),
        )

    def add(self, document: AssetDocument) -> None:
        self._t.add(document)

    def update(self, document: AssetDocument) -> None:
        self._t.update(document)


class MemoryFirmware:
    def __init__(self) -> None:
        self._s: _Stream[FirmwareRecord] = _Stream(lambda r: r.asset_id)

    def for_asset(self, asset_id: AssetId) -> list[FirmwareRecord]:
        return self._s.get(asset_id)

    def append(self, record: FirmwareRecord) -> None:
        self._s.append(record, record.id, record.sequence)


class MemoryKitTemplates:
    def __init__(self) -> None:
        self._t: _Table[KitTemplate] = _Table("kit template", {"name": lambda t: t.name.lower()})

    def get(self, template_id: KitTemplateId) -> KitTemplate | None:
        return self._t.rows.get(template_id)

    def list(self, *, include_inactive: bool = False) -> list[KitTemplate]:
        rows = [t for t in self._t.rows.values() if include_inactive or t.is_active]
        return sorted(rows, key=lambda t: t.name)

    def add(self, template: KitTemplate) -> None:
        self._t.add(template)

    def update(self, template: KitTemplate) -> None:
        self._t.update(template)


class MemoryKits:
    def __init__(self) -> None:
        self._t: _Table[Kit] = _Table("kit", {"code": lambda k: k.code})

    def get(self, kit_id: KitId) -> Kit | None:
        return self._t.rows.get(kit_id)

    def find_by_code(self, code: str) -> Kit | None:
        normalised = code.strip().upper()
        if not normalised.startswith("KIT-"):
            normalised = f"KIT-{normalised}"
        return self._t.find("code", normalised)

    def find_by_member(self, asset_id: AssetId) -> Kit | None:
        return next(
            (k for k in self._t.rows.values() if not k.is_deleted and asset_id in k.members), None
        )

    def list(self, *, include_deleted: bool = False) -> list[Kit]:
        kits = [k for k in self._t.rows.values() if include_deleted or not k.is_deleted]
        return sorted(kits, key=lambda k: k.code)

    def add(self, kit: Kit) -> None:
        self._t.add(kit)

    def update(self, kit: Kit) -> None:
        self._t.update(kit)


class MemoryReorderLevels:
    def __init__(self) -> None:
        self._t: _Table[ReorderLevel] = _Table(
            "reorder level", {"item_type_and_site": lambda r: (r.item_type_id, r.location_id)}
        )

    def get(self, level_id: uuid.UUID) -> ReorderLevel | None:
        return self._t.rows.get(level_id)

    def list(self) -> list[ReorderLevel]:
        return sorted(
            self._t.rows.values(), key=lambda r: (str(r.item_type_id), str(r.location_id))
        )

    def add(self, level: ReorderLevel) -> None:
        self._t.add(level)

    def update(self, level: ReorderLevel) -> None:
        self._t.update(level)


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


class MemoryProjects:
    def __init__(self) -> None:
        self._t: _Table[Project] = _Table("project", {"code": lambda p: p.code})

    def get(self, project_id: ProjectId) -> Project | None:
        return self._t.rows.get(project_id)

    def find_by_code(self, code: str) -> Project | None:
        normalised = code.strip().upper().replace(" ", "-")
        if not normalised.startswith("PRJ-"):
            normalised = f"PRJ-{normalised}"
        return self._t.find("code", normalised)

    def list(self, *, include_deleted: bool = False) -> list[Project]:
        rows = [p for p in self._t.rows.values() if include_deleted or not p.is_deleted]
        return sorted(rows, key=lambda p: (p.starts_on, p.code), reverse=True)

    def add(self, project: Project) -> None:
        self._t.add(project)

    def update(self, project: Project) -> None:
        self._t.update(project)


class MemoryDeployments:
    def __init__(self) -> None:
        self._t: _Table[Deployment] = _Table("deployment", {})

    def get(self, deployment_id: DeploymentId) -> Deployment | None:
        return self._t.rows.get(deployment_id)

    def for_project(self, project_id: ProjectId) -> list[Deployment]:
        rows = [d for d in self._t.rows.values() if d.project_id == project_id]
        return sorted(rows, key=lambda d: (d.created_at, str(d.id)))

    def list(self) -> list[Deployment]:
        return sorted(self._t.rows.values(), key=lambda d: (d.created_at, str(d.id)), reverse=True)

    def add(self, deployment: Deployment) -> None:
        self._t.add(deployment)

    def update(self, deployment: Deployment) -> None:
        self._t.update(deployment)


class MemorySorties:
    def __init__(self) -> None:
        self._t: _Table[Sortie] = _Table("flight log", {})

    def get(self, sortie_id: SortieId) -> Sortie | None:
        return self._t.rows.get(sortie_id)

    def for_project(self, project_id: ProjectId) -> list[Sortie]:
        rows = [r for r in self._t.rows.values() if r.project_id == project_id]
        return sorted(rows, key=lambda r: (r.flown_on, r.recorded_at, str(r.id)))

    def list(self) -> list[Sortie]:
        return sorted(self._t.rows.values(), key=lambda r: (r.flown_on, r.recorded_at, str(r.id)))

    def add(self, sortie: Sortie) -> None:
        self._t.add(sortie)

    def update(self, sortie: Sortie) -> None:
        self._t.update(sortie)


class MemorySurveySessions:
    def __init__(self) -> None:
        self._t: _Table[SurveySession] = _Table("survey session", {})

    def get(self, session_id: SurveySessionId) -> SurveySession | None:
        return self._t.rows.get(session_id)

    def for_project(self, project_id: ProjectId) -> list[SurveySession]:
        rows = [r for r in self._t.rows.values() if r.project_id == project_id]
        return sorted(rows, key=lambda r: (r.surveyed_on, r.recorded_at, str(r.id)))

    def list(self) -> list[SurveySession]:
        return sorted(
            self._t.rows.values(), key=lambda r: (r.surveyed_on, r.recorded_at, str(r.id))
        )

    def add(self, session: SurveySession) -> None:
        self._t.add(session)

    def update(self, session: SurveySession) -> None:
        self._t.update(session)


class MemoryReservations:
    def __init__(self) -> None:
        self._t: _Table[Reservation] = _Table("reservation", {})

    def get(self, reservation_id: ReservationId) -> Reservation | None:
        return self._t.rows.get(reservation_id)

    def for_project(self, project_id: ProjectId) -> list[Reservation]:
        return [r for r in self.list() if r.project_id == project_id]

    def list(self) -> list[Reservation]:
        return sorted(self._t.rows.values(), key=lambda r: (r.starts_on, r.requested_at, str(r.id)))

    def add(self, reservation: Reservation) -> None:
        self._t.add(reservation)

    def update(self, reservation: Reservation) -> None:
        self._t.update(reservation)


class MemoryBookings:
    def __init__(self) -> None:
        self._s: _Stream[BookingEvent] = _Stream(lambda e: e.asset_id)

    def for_asset(self, asset_id: AssetId) -> list[BookingEvent]:
        return self._s.get(asset_id)

    def append(self, event: BookingEvent) -> None:
        self._s.append(event, event.id, event.sequence)


class MemoryMaintenanceTasks:
    def __init__(self) -> None:
        self._t: _Table[MaintenanceTask] = _Table("maintenance task", {})

    def get(self, task_id: MaintenanceTaskId) -> MaintenanceTask | None:
        return self._t.rows.get(task_id)

    def list(self, *, include_inactive: bool = False) -> list[MaintenanceTask]:
        rows = [t for t in self._t.rows.values() if include_inactive or t.is_active]
        return sorted(rows, key=lambda t: (str(t.item_type_id), t.name, str(t.id)))

    def add(self, task: MaintenanceTask) -> None:
        self._t.add(task)

    def update(self, task: MaintenanceTask) -> None:
        self._t.update(task)


class MemoryCompletions:
    def __init__(self) -> None:
        self._s: _Stream[TaskCompletion] = _Stream(lambda c: c.asset_id)

    def for_asset(self, asset_id: AssetId) -> list[TaskCompletion]:
        return self._s.get(asset_id)

    def append(self, completion: TaskCompletion) -> None:
        self._s.append(completion, completion.id, completion.sequence)


class MemoryDefects:
    def __init__(self) -> None:
        self._t: _Table[Defect] = _Table("defect", {"number": lambda d: d.number})

    def get(self, defect_id: DefectId) -> Defect | None:
        return self._t.rows.get(defect_id)

    def for_asset(self, asset_id: AssetId) -> list[Defect]:
        return [d for d in self.list() if d.asset_id == asset_id]

    def list(self) -> list[Defect]:
        return sorted(self._t.rows.values(), key=lambda d: (d.reported_at, d.number), reverse=True)

    def add(self, defect: Defect) -> None:
        self._t.add(defect)

    def update(self, defect: Defect) -> None:
        self._t.update(defect)


class MemoryWorkOrders:
    def __init__(self) -> None:
        self._t: _Table[WorkOrder] = _Table("work order", {"number": lambda w: w.number})

    def get(self, work_order_id: WorkOrderId) -> WorkOrder | None:
        return self._t.rows.get(work_order_id)

    def for_asset(self, asset_id: AssetId) -> list[WorkOrder]:
        return [w for w in self.list() if w.asset_id == asset_id]

    def list(self) -> list[WorkOrder]:
        return sorted(self._t.rows.values(), key=lambda w: (w.opened_at, w.number), reverse=True)

    def add(self, order: WorkOrder) -> None:
        self._t.add(order)

    def update(self, order: WorkOrder) -> None:
        self._t.update(order)


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
        sites=MemorySites(),
        item_types=MemoryItemTypes(),
        assets=MemoryAssets(),
        status_events=MemoryStatusEvents(),
        usage=MemoryUsage(),
        stock=MemoryStock(),
        configuration=MemoryConfiguration(),
        documents=MemoryDocuments(),
        firmware=MemoryFirmware(),
        kit_templates=MemoryKitTemplates(),
        kits=MemoryKits(),
        reorder_levels=MemoryReorderLevels(),
        projects=MemoryProjects(),
        deployments=MemoryDeployments(),
        sorties=MemorySorties(),
        survey_sessions=MemorySurveySessions(),
        reservations=MemoryReservations(),
        bookings=MemoryBookings(),
        maintenance_tasks=MemoryMaintenanceTasks(),
        completions=MemoryCompletions(),
        defects=MemoryDefects(),
        work_orders=MemoryWorkOrders(),
        audit=MemoryAudit(),
        commands=MemoryCommandLog(),
    )
