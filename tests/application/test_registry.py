from datetime import date, timedelta
from decimal import Decimal

import pytest

from ims.domain.assets.catalogue import DEFAULT_CATALOGUE, Meter
from ims.domain.assets.documents import DocumentKind
from ims.domain.assets.status import Serviceability, StatusChange
from ims.domain.common.errors import (
    ConflictError,
    NotFound,
    PermissionDenied,
    RuleViolation,
)
from ims.domain.common.ids import AssetId, DocumentId, KitId, LocationId, uuid7
from ims.domain.kits import DEFAULT_TEMPLATES
from ims.domain.sites.site import SiteKind
from ims.domain.stock.ledger import MovementKind
from tests.application.conftest import App

TYPES = {t.code: t for t in DEFAULT_CATALOGUE}
PDF = b"%PDF-1.7\n" + b"\x00" * 32


def register(app: App, code: str, tag: str, serial: str | None = None, **extra: object) -> AssetId:
    item_type = TYPES[code]
    return app.assets.register(
        app.ctx(app.admin),
        item_type_id=item_type.id,
        asset_tag=tag,
        serial_number=serial or (f"SN-{tag}" if item_type.tracking.value == "serialized" else None),
        **extra,  # type: ignore[arg-type]
    )


class TestTags:
    def test_next_tag_per_prefix(self, app: App) -> None:
        drone = TYPES["DRONE_AIRFRAME"]
        assert app.assets.suggest_tag(app.actor(app.pilot), drone.id) == "DRN-0001"
        register(app, "DRONE_AIRFRAME", "DRN-0007")
        register(app, "DRONE_AIRFRAME", "DRN-X12")  # non-numeric tags are ignored
        assert app.assets.suggest_tag(app.actor(app.pilot), drone.id) == "DRN-0008"

    def test_home_site(self, app: App) -> None:
        site = app.sites.create(
            app.ctx(app.admin), code="MAIN", name="Main store", kind=SiteKind.STORE
        )
        drone = register(app, "DRONE_AIRFRAME", "DRN-0001", home_site_id=site)
        overview = app.registry.overview(app.actor(app.pilot), drone)
        assert overview.home_site is not None and overview.home_site.code == "MAIN"


class TestConfiguration:
    def test_install_swap_and_remove(self, app: App) -> None:
        drone = register(app, "DRONE_AIRFRAME", "DRN-0001")
        spare = register(app, "DRONE_AIRFRAME", "DRN-0002")
        m1 = register(app, "MOTOR", "MOT-0001")
        m2 = register(app, "MOTOR", "MOT-0002")
        app.registry.install(app.ctx(app.admin), m1, drone, "Motor 1")
        app.registry.install(app.ctx(app.admin), m2, drone, "Motor 2")
        overview = app.registry.overview(app.actor(app.pilot), drone)
        assert [(c.asset.asset_tag, c.position) for c in overview.components] == [
            ("MOT-0001", "Motor 1"), ("MOT-0002", "Motor 2"),
        ]  # fmt: skip
        part = app.registry.overview(app.actor(app.pilot), m1)
        assert part.installed_on is not None and part.installed_on[1] == "Motor 1"

        with pytest.raises(RuleViolation, match="already installed"):
            app.registry.install(app.ctx(app.admin), m1, spare, "Motor 1")
        with pytest.raises(
            RuleViolation, match="position Motor 1 on this airframe is already taken"
        ):
            app.registry.install(
                app.ctx(app.admin), register(app, "MOTOR", "MOT-0003"), drone, "motor 1"
            )

        ctx = app.ctx(app.admin)
        app.registry.remove(ctx, m1, "Bearing noise")
        app.registry.remove(ctx, m1, "Bearing noise")  # retry is harmless
        app.registry.install(app.ctx(app.admin), m1, spare, "Motor 4")
        assert [
            c.asset.asset_tag for c in app.registry.overview(app.actor(app.admin), drone).components
        ] == ["MOT-0002"]
        assert len(app.storage.configuration.for_component(m1)) == 3
        with pytest.raises(RuleViolation, match="not installed"):
            app.registry.remove(app.ctx(app.admin), register(app, "MOTOR", "MOT-0009"))

    def test_install_rules(self, app: App) -> None:
        drone = register(app, "DRONE_AIRFRAME", "DRN-0001")
        battery = register(app, "DRONE_BATTERY", "BAT-0001")
        motor = register(app, "MOTOR", "MOT-0001")
        with pytest.raises(RuleViolation, match="not a component"):
            app.registry.install(app.ctx(app.admin), battery, drone)
        with pytest.raises(RuleViolation, match="only be installed on a drone airframe"):
            app.registry.install(app.ctx(app.admin), motor, battery)
        app.assets.change_status(
            app.ctx(app.pilot),
            motor,
            StatusChange(serviceability=Serviceability.UNSERVICEABLE, reason="Cracked"),
        )
        with pytest.raises(RuleViolation, match="grounded or retired components"):
            app.registry.install(app.ctx(app.admin), motor, drone)
        with pytest.raises(PermissionDenied):
            app.registry.install(app.ctx(app.pilot), motor, drone)
        with pytest.raises(NotFound):
            app.registry.install(app.ctx(app.admin), AssetId(uuid7()), drone)


class TestDocumentsAndCompliance:
    def test_drone_needs_uin_and_insurance(self, app: App) -> None:
        drone = register(app, "DRONE_AIRFRAME", "DRN-0001")
        actor = app.actor(app.admin)
        assert app.registry.overview(actor, drone).problems == [
            ("danger", "UIN (Digital Sky) missing"),
            ("danger", "Third-party insurance missing"),
        ]
        app.registry.add_document(
            app.ctx(app.admin), drone, kind=DocumentKind.UIN, reference="UA0012345678"
        )
        soon = app.clock.today() + timedelta(days=10)
        doc = app.registry.add_document(
            app.ctx(app.admin),
            drone,
            kind=DocumentKind.INSURANCE,
            reference="POL-1",
            valid_until=soon,
            file_content=PDF,
        )
        overview = app.registry.overview(actor, drone)
        assert overview.problems == [("warning", f"Third-party insurance expires {soon:%d %b %Y}")]
        statuses = {d.kind: s for d, s in overview.documents}
        assert statuses == {DocumentKind.UIN: "permanent", DocumentKind.INSURANCE: "expiring"}
        stored = app.storage.documents.get(doc)
        assert stored is not None and stored.file is not None and app.files.get(stored.file) == PDF

        app.registry.update_document(app.ctx(app.admin), doc, 1, valid_until=date(2028, 1, 1))
        assert app.registry.overview(actor, drone).problems == []
        alerts_before = app.registry.compliance_alerts(actor)
        assert alerts_before == []
        app.registry.remove_document(app.ctx(app.admin), doc, 2)
        alerts = app.registry.compliance_alerts(actor)
        assert [(a.asset.asset_tag, a.message) for a in alerts] == [
            ("DRN-0001", "Third-party insurance missing")
        ]

    def test_calibration_for_gnss_and_rules(self, app: App) -> None:
        receiver = register(app, "GNSS_RECEIVER", "GNS-0001")
        tripod = register(app, "TRIPOD", "TRP-0001")
        expired = app.clock.today() - timedelta(days=1)
        app.registry.add_document(app.ctx(app.admin), receiver, kind=DocumentKind.CALIBRATION,
                                  reference="CAL-77", valid_until=expired)  # fmt: skip
        assert app.registry.overview(app.actor(app.admin), receiver).problems[0][0] == "danger"
        with pytest.raises(RuleViolation, match="does not track calibration"):
            app.registry.add_document(
                app.ctx(app.admin),
                tripod,
                kind=DocumentKind.CALIBRATION,
                reference="X",
                valid_until=date(2030, 1, 1),
            )
        with pytest.raises(RuleViolation, match="drone airframes only"):
            app.registry.add_document(
                app.ctx(app.admin), tripod, kind=DocumentKind.UIN, reference="UA1"
            )
        with pytest.raises(RuleViolation, match="needs a valid-until date"):
            app.registry.add_document(
                app.ctx(app.admin), receiver, kind=DocumentKind.CALIBRATION, reference="C"
            )
        with pytest.raises(RuleViolation, match="Only JPEG, PDF, PNG"):
            app.registry.add_document(app.ctx(app.admin), receiver, kind=DocumentKind.OTHER,
                                      reference="R", file_content=b"MZ exe")  # fmt: skip

    def test_document_conflicts_and_permissions(self, app: App) -> None:
        drone = register(app, "DRONE_AIRFRAME", "DRN-0001")
        doc = app.registry.add_document(
            app.ctx(app.admin), drone, kind=DocumentKind.UIN, reference="UA1"
        )
        app.registry.update_document(app.ctx(app.admin), doc, 1, notes="checked")
        with pytest.raises(ConflictError):
            app.registry.update_document(app.ctx(app.admin), doc, 1, notes="stale")
        with pytest.raises(RuleViolation, match="cannot be changed here: asset_id"):
            app.registry.update_document(app.ctx(app.admin), doc, 2, asset_id=drone)
        with pytest.raises(PermissionDenied):
            app.registry.add_document(
                app.ctx(app.pilot), drone, kind=DocumentKind.UIN, reference="UA2"
            )
        with pytest.raises(NotFound):
            app.registry.remove_document(app.ctx(app.admin), DocumentId(uuid7()), 1)

    def test_retired_assets_raise_no_alerts(self, app: App) -> None:
        drone = register(app, "DRONE_AIRFRAME", "DRN-0001")
        app.assets.change_status(
            app.ctx(app.admin),
            drone,
            StatusChange(serviceability=Serviceability.RETIRED, reason="Crashed"),
        )
        assert app.registry.compliance_alerts(app.actor(app.admin)) == []


class TestFirmware:
    def test_history(self, app: App) -> None:
        drone = register(
            app, "DRONE_AIRFRAME", "DRN-0001", opening_balances={Meter.HOURS: Decimal(12)}
        )
        app.registry.record_firmware(app.ctx(app.admin), drone, "v04.01.0300", date(2026, 3, 1))
        app.registry.record_firmware(
            app.ctx(app.admin), drone, "v04.02.0100", date(2026, 9, 1), "Gimbal fix"
        )
        overview = app.registry.overview(app.actor(app.pilot), drone)
        assert [f.version for f in overview.firmware] == ["v04.01.0300", "v04.02.0100"]
        assert overview.meters == {Meter.HOURS: Decimal(12)}
        with pytest.raises(RuleViolation, match="already the current firmware"):
            app.registry.record_firmware(
                app.ctx(app.admin), drone, "v04.02.0100", date(2026, 10, 1)
            )
        with pytest.raises(RuleViolation, match="must not go backwards"):
            app.registry.record_firmware(app.ctx(app.admin), drone, "v05", date(2026, 1, 1))


class TestKits:
    def test_build_a_kit_from_a_template(self, app: App) -> None:
        assert app.kits.install_default_templates(app.ctx(app.admin)) == 2
        assert app.kits.install_default_templates(app.ctx(app.admin)) == 0
        dgps_template = DEFAULT_TEMPLATES[1]
        kit_id = app.kits.create(app.ctx(app.admin), code="dgps-01", name="DGPS set 1",
                                 template_id=dgps_template.id)  # fmt: skip
        overview = app.kits.get(app.actor(app.surveyor), kit_id)
        assert overview.kit.code == "KIT-DGPS-01" and overview.completeness is not None
        assert not overview.completeness.complete

        base = register(app, "GNSS_RECEIVER", "GNS-0001")
        rover = register(app, "GNSS_RECEIVER", "GNS-0002")
        app.kits.add_member(app.ctx(app.admin), kit_id, 1, base)
        app.kits.add_member(app.ctx(app.admin), kit_id, 2, rover)
        overview = app.kits.get(app.actor(app.admin), kit_id)
        missing = overview.completeness.missing if overview.completeness else {}
        assert TYPES["GNSS_RECEIVER"].id not in missing and TYPES["TRIPOD"].id in missing
        assert app.registry.overview(app.actor(app.admin), base).kit is not None

        other = app.kits.create(app.ctx(app.admin), code="KIT-DGPS-02", name="DGPS set 2")
        with pytest.raises(RuleViolation, match="already in KIT-DGPS-01"):
            app.kits.add_member(app.ctx(app.admin), other, 1, base)
        with pytest.raises(RuleViolation, match="already in this kit"):
            app.kits.add_member(app.ctx(app.admin), kit_id, 3, base)

        app.kits.remove_member(app.ctx(app.admin), kit_id, 3, rover)
        app.kits.add_member(app.ctx(app.admin), other, 1, rover)
        app.kits.delete(app.ctx(app.admin), kit_id, 4)
        app.kits.add_member(
            app.ctx(app.admin), other, 2, base
        )  # free again after the kit is broken up
        assert [k.kit.code for k in app.kits.list_kits(app.actor(app.admin))] == ["KIT-DGPS-02"]

    def test_kit_rules(self, app: App) -> None:
        kit = app.kits.create(app.ctx(app.admin), code="KIT-A1", name="A")
        with pytest.raises(RuleViolation, match="already in use"):
            app.kits.create(app.ctx(app.admin), code="a1", name="Copy")
        with pytest.raises(NotFound):
            app.kits.create(
                app.ctx(app.admin), code="KIT-B1", name="B", template_id=DEFAULT_TEMPLATES[0].id
            )
        with pytest.raises(ConflictError):
            app.kits.update(app.ctx(app.admin), kit, 5, name="Stale")
        with pytest.raises(RuleViolation, match="cannot be changed here: members"):
            app.kits.update(app.ctx(app.admin), kit, 1, members=())
        with pytest.raises(PermissionDenied):
            app.kits.create(app.ctx(app.pilot), code="KIT-C1", name="C")
        with pytest.raises(NotFound):
            app.kits.get(app.actor(app.admin), KitId(uuid7()))
        app.kits.update(app.ctx(app.admin), kit, 1, name="Renamed")
        assert app.kits.get(app.actor(app.admin), kit).kit.name == "Renamed"


class TestReorderLevels:
    def test_levels_and_low_stock(self, app: App) -> None:
        banner = TYPES["GCP_BANNER"].id
        store = app.sites.create(
            app.ctx(app.admin), code="MAIN", name="Main store", kind=SiteKind.STORE
        )
        app.stock.set_reorder_level(app.ctx(app.admin), banner, store, 20)
        app.stock.record(app.ctx(app.admin), item_type_id=banner, location_id=store,
                         kind=MovementKind.RECEIVED, quantity=25)  # fmt: skip
        [row] = app.stock.by_site(app.actor(app.surveyor), banner)
        assert (row.on_hand, row.reorder_level, row.low) == (25, 20, False)
        app.stock.set_reorder_level(app.ctx(app.admin), banner, store, 30)
        app.stock.set_reorder_level(
            app.ctx(app.admin), banner, store, 30
        )  # unchanged: no new version
        assert app.stock.by_site(app.actor(app.admin), banner)[0].low
        with pytest.raises(RuleViolation, match="not counted stock"):
            app.stock.set_reorder_level(app.ctx(app.admin), TYPES["TRIPOD"].id, store, 1)
        with pytest.raises(NotFound):
            app.stock.set_reorder_level(app.ctx(app.admin), banner, LocationId(uuid7()), 1)
        with pytest.raises(PermissionDenied):
            app.stock.set_reorder_level(app.ctx(app.surveyor), banner, store, 1)
