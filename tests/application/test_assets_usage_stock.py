from datetime import date
from decimal import Decimal

import pytest

from ims.domain.assets.catalogue import DEFAULT_CATALOGUE, Category, Discipline, ItemType, Meter
from ims.domain.assets.catalogue import TrackingMode as T
from ims.domain.assets.status import Custody, Serviceability, StatusChange
from ims.domain.common.errors import (
    ConflictError,
    InvalidTransition,
    NotFound,
    PermissionDenied,
    RuleViolation,
)
from ims.domain.common.ids import AssetId, EntryId, ItemTypeId, LocationId, ProjectId, uuid7
from ims.domain.stock.ledger import MovementKind
from ims.domain.usage.ledger import UsageSource
from tests.application.conftest import App

TYPES = {t.code: t for t in DEFAULT_CATALOGUE}
DRONE, BANNER = TYPES["DRONE_AIRFRAME"], TYPES["GCP_BANNER"]
PROJECT = ProjectId(uuid7())
STORE = LocationId(uuid7())


def register_drone(app: App, tag: str = "DRN-0001", serial: str = "SN-1") -> AssetId:
    return app.assets.register(
        app.ctx(app.admin),
        item_type_id=DRONE.id,
        asset_tag=tag,
        serial_number=serial,
        make="Example Aero",
        acquired_on=date(2025, 4, 1),
        opening_balances={Meter.HOURS: Decimal("120.50"), Meter.CYCLES: Decimal(340)},
    )


class TestCatalogue:
    def test_defaults_installed_once(self, app: App) -> None:
        assert len(app.catalogue.list_item_types(app.actor(app.pilot))) == len(DEFAULT_CATALOGUE)
        assert app.catalogue.install_defaults(app.ctx(app.admin)) == 0
        assert app.catalogue.get(app.actor(app.pilot), BANNER.id) == BANNER
        with pytest.raises(NotFound):
            app.catalogue.get(app.actor(app.pilot), ItemTypeId(uuid7()))

    def test_admin_adds_item_type(self, app: App) -> None:
        ctx = app.ctx(app.admin)
        new_type = ItemType.build(
            id=ctx.derive("item_type"), code="RANGEFINDER", name="Laser rangefinder",
            category=Category.FIELD_ELECTRONICS, discipline=Discipline.SURVEY,
            tracking=T.TAGGED, tag_prefix="RNG", tracks_calibration=True,
        )  # fmt: skip
        assert app.catalogue.add_item_type(ctx, new_type) == new_type.id
        assert app.catalogue.add_item_type(ctx, new_type) == new_type.id  # retry
        clash_ctx = app.ctx(app.admin)
        clash = new_type.model_copy(update={"id": clash_ctx.derive("item_type")})
        with pytest.raises(RuleViolation, match="already in use"):
            app.catalogue.add_item_type(clash_ctx, clash)
        with pytest.raises(RuleViolation, match="derived from the command"):
            app.catalogue.add_item_type(app.ctx(app.admin), new_type)
        with pytest.raises(PermissionDenied):
            app.catalogue.install_defaults(app.ctx(app.pilot))


class TestAssets:
    def test_register_with_opening_balances(self, app: App) -> None:
        asset_id = register_drone(app)
        actor = app.actor(app.pilot)
        assert app.assets.get(actor, asset_id).asset_tag == "DRN-0001"
        assert app.usage.totals(actor, asset_id) == {
            Meter.HOURS: Decimal("120.50"),
            Meter.CYCLES: Decimal(340),
        }
        assert app.assets.status(actor, asset_id).is_deployable
        assert [a.id for a in app.assets.list_assets(actor, item_type_id=DRONE.id)] == [asset_id]

    def test_register_is_idempotent(self, app: App) -> None:
        ctx = app.ctx(app.admin)
        kwargs = {"item_type_id": DRONE.id, "asset_tag": "DRN-0009", "serial_number": "S9",
                  "opening_balances": {Meter.HOURS: Decimal(5)}}  # fmt: skip
        first = app.assets.register(ctx, **kwargs)  # type: ignore[arg-type]
        second = app.assets.register(ctx, **kwargs)  # type: ignore[arg-type]
        assert first == second
        assert len(app.storage.usage.for_asset(first)) == 1

    def test_duplicates_and_type_rules(self, app: App) -> None:
        register_drone(app)
        with pytest.raises(RuleViolation) as caught:
            register_drone(app, tag="DRN-0001", serial="SN-1")
        assert caught.value.problems == (
            "Asset tag DRN-0001 is already in use.",
            "Serial number SN-1 is already registered (asset DRN-0001).",
        )
        with pytest.raises(RuleViolation, match="counted stock"):
            app.assets.register(app.ctx(app.admin), item_type_id=BANNER.id, asset_tag="GC-0001")
        with pytest.raises(PermissionDenied):
            register_drone(app.__class__(**{**app.__dict__, "admin": app.pilot}))
        with pytest.raises(NotFound):
            app.assets.register(app.ctx(app.admin), item_type_id=ItemTypeId(uuid7()),
                                asset_tag="DRN-0002")  # fmt: skip

    def test_opening_balance_for_untracked_meter_is_rejected(self, app: App) -> None:
        with pytest.raises(RuleViolation, match="does not track landings"):
            app.assets.register(
                app.ctx(app.admin), item_type_id=TYPES["MOTOR"].id, asset_tag="MOT-0001",
                serial_number="M1", opening_balances={Meter.LANDINGS: Decimal(3)},
            )  # fmt: skip

    def test_update_asset(self, app: App) -> None:
        asset_id = register_drone(app)
        app.assets.update(app.ctx(app.admin), asset_id, 1, notes="New props fitted", model="X8")
        asset = app.assets.get(app.actor(app.admin), asset_id)
        assert (asset.notes, asset.model, asset.version) == ("New props fitted", "X8", 2)
        with pytest.raises(ConflictError):
            app.assets.update(app.ctx(app.admin), asset_id, 1, notes="stale")
        with pytest.raises(RuleViolation, match="cannot be changed here: item_type_id"):
            app.assets.update(app.ctx(app.admin), asset_id, 2, item_type_id=BANNER.id)
        other = register_drone(app, "DRN-0002", "SN-2")
        with pytest.raises(RuleViolation, match="already in use"):
            app.assets.update(app.ctx(app.admin), other, 1, asset_tag="DRN-0001")

    def test_update_retry_is_harmless(self, app: App) -> None:
        asset_id = register_drone(app)
        ctx = app.ctx(app.admin)
        app.assets.update(ctx, asset_id, 1, notes="once")
        app.assets.update(ctx, asset_id, 1, notes="once")
        assert app.assets.get(app.actor(app.admin), asset_id).version == 2


class TestStatusChanges:
    def test_field_cycle_with_defect_and_return_to_service(self, app: App) -> None:
        asset_id = register_drone(app)
        pilot = app.ctx
        deploy = StatusChange(custody=Custody.DEPLOYED, project_id=PROJECT)
        app.assets.change_status(pilot(app.pilot), asset_id, deploy)
        app.assets.change_status(
            pilot(app.pilot), asset_id,
            StatusChange(serviceability=Serviceability.UNSERVICEABLE, reason="Motor 3 vibration"),
        )  # fmt: skip
        app.assets.change_status(pilot(app.pilot), asset_id, StatusChange(custody=Custody.IN_STORE))
        with pytest.raises(PermissionDenied, match=r"maintenance\.certify"):
            app.assets.change_status(
                pilot(app.pilot), asset_id, StatusChange(serviceability=Serviceability.SERVICEABLE)
            )
        app.assets.change_status(
            pilot(app.admin), asset_id, StatusChange(serviceability=Serviceability.SERVICEABLE)
        )
        history = app.assets.history(app.actor(app.admin), asset_id)
        assert [e.sequence for e in history] == [1, 2, 3, 4]
        assert history[1].reason == "Motor 3 vibration"
        assert app.assets.status(app.actor(app.admin), asset_id).is_deployable

    def test_grounded_drone_cannot_be_deployed(self, app: App) -> None:
        asset_id = register_drone(app)
        app.assets.change_status(
            app.ctx(app.pilot), asset_id,
            StatusChange(serviceability=Serviceability.UNSERVICEABLE, reason="Crash"),
        )  # fmt: skip
        with pytest.raises(InvalidTransition, match="cannot be deployed"):
            app.assets.change_status(
                app.ctx(app.pilot), asset_id,
                StatusChange(custody=Custody.DEPLOYED, project_id=PROJECT),
            )  # fmt: skip

    def test_status_retry_appends_once(self, app: App) -> None:
        asset_id = register_drone(app)
        ctx = app.ctx(app.pilot)
        change = StatusChange(custody=Custody.RESERVED)
        app.assets.change_status(ctx, asset_id, change)
        app.assets.change_status(ctx, asset_id, change)
        assert len(app.assets.history(app.actor(app.pilot), asset_id)) == 1

    def test_unknown_asset(self, app: App) -> None:
        with pytest.raises(NotFound):
            app.assets.change_status(app.ctx(app.admin), AssetId(uuid7()),
                                     StatusChange(custody=Custody.RESERVED))  # fmt: skip


class TestUsage:
    def test_record_and_reverse(self, app: App) -> None:
        asset_id = register_drone(app)
        entry_id = app.usage.record(
            app.ctx(app.pilot), asset_id=asset_id, meter=Meter.HOURS, amount=Decimal("1.40"),
            occurred_on=date(2026, 11, 8), source=UsageSource.SORTIE, project_id=PROJECT,
        )  # fmt: skip
        assert app.usage.totals(app.actor(app.pilot), asset_id)[Meter.HOURS] == Decimal("121.90")
        with pytest.raises(PermissionDenied, match=r"usage\.correct"):
            app.usage.reverse(app.ctx(app.pilot), asset_id, entry_id, "typo")
        app.usage.reverse(app.ctx(app.admin), asset_id, entry_id, "Entered against wrong drone")
        assert app.usage.totals(app.actor(app.pilot), asset_id)[Meter.HOURS] == Decimal("120.50")
        with pytest.raises(RuleViolation, match="already been reversed"):
            app.usage.reverse(app.ctx(app.admin), asset_id, entry_id, "again")
        with pytest.raises(NotFound):
            app.usage.reverse(app.ctx(app.admin), asset_id, EntryId(uuid7()), "missing")
        assert len(app.usage.entries(app.actor(app.admin), asset_id)) == 4

    def test_adjustments_are_admin_only(self, app: App) -> None:
        asset_id = register_drone(app)
        kwargs = {"asset_id": asset_id, "meter": Meter.CYCLES, "amount": Decimal(-2),
                  "occurred_on": date(2026, 11, 8), "source": UsageSource.ADJUSTMENT,
                  "note": "Counter correction"}  # fmt: skip
        with pytest.raises(PermissionDenied):
            app.usage.record(app.ctx(app.pilot), **kwargs)  # type: ignore[arg-type]
        app.usage.record(app.ctx(app.admin), **kwargs)  # type: ignore[arg-type]
        assert app.usage.totals(app.actor(app.admin), asset_id)[Meter.CYCLES] == Decimal(338)

    def test_record_retry_and_unknown_asset(self, app: App) -> None:
        asset_id = register_drone(app)
        ctx = app.ctx(app.pilot)
        kwargs = {"asset_id": asset_id, "meter": Meter.LANDINGS, "amount": Decimal(2),
                  "occurred_on": date(2026, 11, 8), "source": UsageSource.SORTIE,
                  "project_id": PROJECT}  # fmt: skip
        first = app.usage.record(ctx, **kwargs)  # type: ignore[arg-type]
        assert app.usage.record(ctx, **kwargs) == first  # type: ignore[arg-type]
        with pytest.raises(NotFound):
            app.usage.record(app.ctx(app.pilot), **{**kwargs, "asset_id": AssetId(uuid7())})  # type: ignore[arg-type]


class TestStock:
    def test_gcp_banners_through_a_survey(self, app: App) -> None:
        admin, surveyor = app.ctx, app.ctx
        app.stock.record(admin(app.admin), item_type_id=BANNER.id, location_id=STORE,
                         kind=MovementKind.RECEIVED, quantity=40)  # fmt: skip
        common = {"item_type_id": BANNER.id, "location_id": STORE, "project_id": PROJECT}
        app.stock.record(surveyor(app.surveyor), kind=MovementKind.ISSUED, quantity=12, **common)  # type: ignore[arg-type]
        app.stock.record(surveyor(app.surveyor), kind=MovementKind.RETURNED, quantity=8, **common)  # type: ignore[arg-type]
        app.stock.record(surveyor(app.surveyor), kind=MovementKind.CONSUMED, quantity=4, **common)  # type: ignore[arg-type]
        pos = app.stock.position(app.actor(app.surveyor), BANNER.id)
        assert (pos.on_hand_at(STORE), pos.outstanding_with(PROJECT), pos.consumed[PROJECT]) == (
            36, 0, 4,
        )  # fmt: skip
        assert len(app.stock.movements(app.actor(app.admin), BANNER.id)) == 4

    def test_crew_cannot_receive_or_adjust(self, app: App) -> None:
        with pytest.raises(PermissionDenied, match=r"stock\.manage"):
            app.stock.record(app.ctx(app.pilot), item_type_id=BANNER.id, location_id=STORE,
                             kind=MovementKind.RECEIVED, quantity=5)  # fmt: skip

    def test_over_issue_is_refused_and_retry_is_harmless(self, app: App) -> None:
        ctx = app.ctx(app.admin)
        kwargs = {"item_type_id": BANNER.id, "location_id": STORE,
                  "kind": MovementKind.RECEIVED, "quantity": 5}  # fmt: skip
        first = app.stock.record(ctx, **kwargs)  # type: ignore[arg-type]
        assert app.stock.record(ctx, **kwargs) == first  # type: ignore[arg-type]
        with pytest.raises(RuleViolation, match="only 5"):
            app.stock.record(app.ctx(app.pilot), item_type_id=BANNER.id, location_id=STORE,
                             kind=MovementKind.ISSUED, quantity=6, project_id=PROJECT)  # fmt: skip
        with pytest.raises(NotFound):
            app.stock.record(app.ctx(app.admin), item_type_id=ItemTypeId(uuid7()),
                             location_id=STORE, kind=MovementKind.RECEIVED, quantity=1)  # fmt: skip


class TestAuditTrail:
    def test_every_command_writes_exactly_one_audit_entry(self, app: App) -> None:
        before = len(app.storage.audit.recent(limit=1000))
        app.clock.advance(minutes=1)
        asset_id = register_drone(app)
        app.clock.advance(minutes=1)
        app.assets.change_status(
            app.ctx(app.pilot), asset_id, StatusChange(custody=Custody.RESERVED)
        )
        entries = app.storage.audit.recent(limit=1000)
        assert len(entries) == before + 2
        assert [e.action for e in entries[:2]] == ["asset.change_status", "asset.register"]
        assert entries[0].at == app.clock.now()
