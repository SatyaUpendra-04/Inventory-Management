"""The storage contract: behaviour every adapter must share (see ims.ports.repository)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import DEFAULT_CATALOGUE, Meter
from ims.domain.assets.status import AssetStatus, Custody, Serviceability, StatusEvent
from ims.domain.audit import AuditEntry
from ims.domain.common.errors import AlreadyExists, ConflictError, NotFound
from ims.domain.common.ids import (
    AssetId,
    CommandId,
    EntryId,
    LocationId,
    ProjectId,
    UserId,
    uuid7,
)
from ims.domain.identity.roles import Role
from ims.domain.identity.user import PilotLicence
from ims.domain.stock.ledger import MovementKind, StockMovement
from ims.domain.usage.ledger import UsageEntry, UsageSource
from ims.ports.repository import CommandRecord, Storage
from tests.fakes import START, make_user

pytestmark = pytest.mark.contract

TYPES = {t.code: t for t in DEFAULT_CATALOGUE}
DRONE = TYPES["DRONE_AIRFRAME"]
BANNER = TYPES["GCP_BANNER"]


def _drone(storage: Storage, tag: str = "DRN-0001", serial: str = "SN-1") -> Asset:
    if storage.item_types.get(DRONE.id) is None:
        storage.item_types.add(DRONE)
    asset = Asset(
        id=AssetId(uuid7()),
        item_type_id=DRONE.id,
        asset_tag=tag,
        serial_number=serial,
        make="Example Aero",
        model="X8",
        acquired_on=date(2025, 4, 1),
        warranty_until=date(2027, 3, 31),
        notes="Mapping drone",
    )
    storage.assets.add(asset)
    return asset


# ---------------------------------------------------------------------- users


class TestUsers:
    def test_round_trip_keeps_every_field(self, storage: Storage) -> None:
        user = make_user(
            Role.PILOT,
            licence=PilotLicence(number="RPC-77", expires_on=date(2029, 6, 30)),
            profile_picture="files/p.png",
            deleted_at=START,
            is_active=False,
        )
        storage.users.add(user)
        assert storage.users.get(user.id) == user

    def test_lookups_are_case_insensitive_on_normalised_fields(self, storage: Storage) -> None:
        user = make_user(Role.SURVEYOR)
        storage.users.add(user)
        assert storage.users.find_by_username(user.username.upper()) == user
        assert storage.users.find_by_email(user.email.upper()) == user
        assert storage.users.find_by_employee_id(user.employee_id.lower()) == user
        assert storage.users.get(UserId(uuid7())) is None

    def test_same_id_twice_is_already_exists(self, storage: Storage) -> None:
        user = make_user()
        storage.users.add(user)
        with pytest.raises(AlreadyExists):
            storage.users.add(user)

    @pytest.mark.parametrize("field", ["username", "employee_id", "email"])
    def test_unique_fields(self, storage: Storage, field: str) -> None:
        first = make_user()
        storage.users.add(first)
        clash = make_user(**{field: getattr(first, field)})
        with pytest.raises(ConflictError) as caught:
            storage.users.add(clash)
        assert not isinstance(caught.value, AlreadyExists)

    def test_update_requires_the_next_version(self, storage: Storage) -> None:
        user = make_user()
        storage.users.add(user)
        updated = user.next_version(full_name="Renamed")
        storage.users.update(updated)
        assert storage.users.get(user.id) == updated
        with pytest.raises(ConflictError):
            storage.users.update(user.next_version(full_name="Stale edit"))
        with pytest.raises(NotFound):
            storage.users.update(make_user().next_version(full_name="Ghost"))

    def test_update_respects_unique_fields(self, storage: Storage) -> None:
        a, b = make_user(), make_user()
        storage.users.add(a)
        storage.users.add(b)
        with pytest.raises(ConflictError):
            storage.users.update(b.next_version(email=a.email))

    def test_list_and_admin_count(self, storage: Storage) -> None:
        admin = make_user(Role.ADMIN, username="zz-admin")
        inactive_admin = make_user(Role.ADMIN, is_active=False)
        deleted = make_user(Role.SURVEYOR, deleted_at=START, username="aa-deleted")
        pilot = make_user(Role.PILOT, username="mm-pilot")
        for u in (admin, inactive_admin, deleted, pilot):
            storage.users.add(u)
        names = [u.username for u in storage.users.list()]
        assert names == sorted(names)
        assert deleted.username not in names
        assert deleted.username in [u.username for u in storage.users.list(include_deleted=True)]
        assert storage.users.count_active_admins() == 1


# ---------------------------------------------------------------------- catalogue & assets


class TestCatalogueAndAssets:
    def test_item_types_round_trip_and_filter(self, storage: Storage) -> None:
        for item_type in DEFAULT_CATALOGUE:
            storage.item_types.add(item_type)
        for item_type in DEFAULT_CATALOGUE:
            assert storage.item_types.get(item_type.id) == item_type
        assert storage.item_types.find_by_code("gcp_banner") == BANNER
        retired = BANNER.next_version(is_active=False)
        storage.item_types.update(retired)
        assert BANNER not in storage.item_types.list()
        assert retired in storage.item_types.list(include_inactive=True)
        with pytest.raises(ConflictError):
            storage.item_types.add(DRONE.model_copy(update={"id": uuid7()}))

    def test_asset_round_trip_and_lookups(self, storage: Storage) -> None:
        asset = _drone(storage)
        assert storage.assets.get(asset.id) == asset
        assert storage.assets.find_by_tag("drn-0001") == asset
        assert storage.assets.find_by_serial(DRONE.id, "sn-1") == asset
        assert storage.assets.find_by_serial(BANNER.id, "SN-1") is None

    def test_asset_tag_unique_and_serial_unique_per_type(self, storage: Storage) -> None:
        _drone(storage)
        with pytest.raises(ConflictError):
            _drone(storage, tag="DRN-0001", serial="SN-2")
        with pytest.raises(ConflictError):
            _drone(storage, tag="DRN-0002", serial="SN-1")

    def test_assets_without_serial_do_not_clash(self, storage: Storage) -> None:
        tripod_type = TYPES["TRIPOD"]
        storage.item_types.add(tripod_type)
        for tag in ("TRP-0001", "TRP-0002"):
            storage.assets.add(
                Asset(id=AssetId(uuid7()), item_type_id=tripod_type.id, asset_tag=tag)
            )
        assert len(storage.assets.list(item_type_id=tripod_type.id)) == 2

    def test_asset_versioning_and_list(self, storage: Storage) -> None:
        a = _drone(storage, "DRN-0002", "SN-2")
        b = _drone(storage, "DRN-0001", "SN-1")
        storage.assets.update(b.next_version(deleted_at=START))
        assert [x.asset_tag for x in storage.assets.list()] == ["DRN-0002"]
        assert len(storage.assets.list(include_deleted=True)) == 2
        with pytest.raises(ConflictError):
            storage.assets.update(a.next_version(notes="x").next_version(notes="y"))


# ---------------------------------------------------------------------- ledgers


def _status_event(asset: Asset, seq: int, before: AssetStatus, after: AssetStatus) -> StatusEvent:
    return StatusEvent(
        id=EntryId(uuid7()), asset_id=asset.id, sequence=seq, command_id=CommandId(uuid7()),
        recorded_at=START + timedelta(minutes=seq), recorded_by=UserId(uuid7()),
        before=before, after=after, reason="test", project_id=ProjectId(uuid7()),
    )  # fmt: skip


def _usage(asset: Asset, seq: int, amount: str, **extra: object) -> UsageEntry:
    data: dict[str, object] = {
        "id": EntryId(uuid7()), "asset_id": asset.id, "sequence": seq, "meter": Meter.HOURS,
        "amount": Decimal(amount), "occurred_on": date(2026, 11, 8),
        "source": UsageSource.SORTIE, "recorded_at": START, "recorded_by": UserId(uuid7()),
        "command_id": CommandId(uuid7()), "project_id": ProjectId(uuid7()), "note": "flight",
    }  # fmt: skip
    data.update(extra)
    return UsageEntry.build(**data)


class TestLedgers:
    def test_status_events_append_in_sequence(self, storage: Storage) -> None:
        asset = _drone(storage)
        start = AssetStatus()
        deployed = AssetStatus(custody=Custody.DEPLOYED)
        grounded = AssetStatus(
            serviceability=Serviceability.UNSERVICEABLE, custody=Custody.DEPLOYED
        )
        e1 = _status_event(asset, 1, start, deployed)
        e2 = _status_event(asset, 2, deployed, grounded)
        storage.status_events.append(e1)
        storage.status_events.append(e2)
        assert storage.status_events.for_asset(asset.id) == [e1, e2]
        with pytest.raises(AlreadyExists):
            storage.status_events.append(e2)
        with pytest.raises(ConflictError):  # two people both appending event 2
            storage.status_events.append(_status_event(asset, 2, deployed, start))
        with pytest.raises(ConflictError):  # gaps are not allowed either
            storage.status_events.append(_status_event(asset, 5, grounded, start))

    def test_usage_round_trip_keeps_exact_decimals(self, storage: Storage) -> None:
        asset = _drone(storage)
        entry = _usage(asset, 1, "1.25")
        storage.usage.append(entry)
        stored = storage.usage.for_asset(asset.id)
        assert stored == [entry]
        assert stored[0].amount == Decimal("1.25")
        assert storage.usage.for_asset(AssetId(uuid7())) == []

    def test_usage_sequence_and_single_reversal(self, storage: Storage) -> None:
        asset = _drone(storage)
        original = _usage(asset, 1, "2.00")
        storage.usage.append(original)
        with pytest.raises(ConflictError):
            storage.usage.append(_usage(asset, 1, "1.00"))
        reversal = _usage(
            asset, 2, "-2.00", source=UsageSource.REVERSAL, reverses=original.id, project_id=None
        )
        storage.usage.append(reversal)
        with pytest.raises(ConflictError):
            storage.usage.append(
                _usage(
                    asset,
                    3,
                    "-2.00",
                    source=UsageSource.REVERSAL,
                    reverses=original.id,
                    project_id=None,
                )
            )

    def test_stock_movements_per_item_type(self, storage: Storage) -> None:
        storage.item_types.add(BANNER)
        location = LocationId(uuid7())
        moves = [
            StockMovement(
                id=EntryId(uuid7()),
                item_type_id=BANNER.id,
                sequence=n,
                location_id=location,
                kind=MovementKind.RECEIVED,
                quantity=10 * n,
                recorded_at=START,
                recorded_by=UserId(uuid7()),
                command_id=CommandId(uuid7()),
                reason="delivery",
            )
            for n in (1, 2)
        ]
        for m in moves:
            storage.stock.append(m)
        assert storage.stock.for_item_type(BANNER.id) == moves
        with pytest.raises(ConflictError):
            storage.stock.append(moves[0].model_copy(update={"id": uuid7()}))


# ---------------------------------------------------------------------- audit & commands


class TestAuditAndCommands:
    def test_audit_queries(self, storage: Storage) -> None:
        entries = [
            AuditEntry(
                id=EntryId(uuid7()),
                command_id=CommandId(uuid7()),
                at=START + timedelta(seconds=n),
                actor_id=None if n == 0 else UserId(uuid7()),
                action="asset.update",
                entity="asset",
                entity_id=f"A{n % 2}",
                before={"notes": "old", "n": n} if n else None,
                after={"notes": "new", "nested": [1, 2]},
            )
            for n in range(4)
        ]
        for e in entries:
            storage.audit.append(e)
        assert storage.audit.for_entity("asset", "A0") == [entries[0], entries[2]]
        assert storage.audit.recent(limit=2) == [entries[3], entries[2]]
        with pytest.raises(AlreadyExists):
            storage.audit.append(entries[0])

    def test_command_log(self, storage: Storage) -> None:
        record = CommandRecord(
            command_id=CommandId(uuid7()), action="asset.register", actor_id=UserId(uuid7()),
            completed_at=START, result_id="abc",
        )  # fmt: skip
        assert storage.commands.get(record.command_id) is None
        storage.commands.record(record)
        assert storage.commands.get(record.command_id) == record
        with pytest.raises(AlreadyExists):
            storage.commands.record(record)
