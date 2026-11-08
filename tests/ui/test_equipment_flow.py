"""Equipment, kits and GCP stock screens, driven through their view-models with the real QML
loaded (so the pages and sheets involved are also checked for QML warnings)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QDesktopServices

from ims.ui.app import UiContext
from ims.ui.viewmodels.equipment import available_actions
from tests.ui.conftest import settle, warnings_of

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def no_external_viewer(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Label printing opens the PDF; record the request instead of launching a viewer."""
    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    return opened


def item_type(ui: UiContext, name: str) -> dict[str, Any]:
    return next(t for t in ui.equipment.itemTypes() if t["label"].split("  ·  ")[0] == name)


def add_site(ui: UiContext, code: str, name: str) -> str:
    ui.sites.create({"code": code, "name": name, "kind": "store", "status": "active"})
    settle(ui)
    ui.equipment.refresh()
    settle(ui)
    return str(ui.sites.model.find("code", code)["siteId"])


def register(ui: UiContext, type_name: str, serial: str = "", **extra: str) -> dict[str, Any]:
    kind = item_type(ui, type_name)
    tag = ui.equipment.suggestTag(kind["value"])
    ui.equipment.register({"itemTypeId": kind["value"], "tag": tag, "serial": serial, **extra})
    settle(ui)
    assert ui.equipment.property("error") == "", ui.equipment.property("error")
    row = ui.equipment.model.find("tag", tag)
    assert row, f"{tag} not listed"
    return row


def open_asset(ui: UiContext, asset_id: str) -> dict[str, Any]:
    ui.equipment.openAsset(asset_id)
    settle(ui)
    return dict(ui.equipment.property("detail"))


def sheet(ui: UiContext, class_prefix: str) -> QObject:
    window = ui.engine.rootObjects()[0]
    found = next(
        (
            o
            for o in window.findChildren(QObject)
            if o.metaObject().className().startswith(class_prefix)
        ),
        None,
    )
    assert found is not None, f"{class_prefix} not loaded"
    return found


# ---------------------------------------------------------------------- equipment


def test_signing_in_installs_the_catalogue_and_filters_work(ui: UiContext) -> None:
    ui.shell.navigate("equipment")
    settle(ui, 300)
    names = [t["label"].split("  ·  ")[0] for t in ui.equipment.itemTypes()]
    assert {"Drone airframe", "Motor", "DGPS receiver (base / rover)", "Tripod"} <= set(names)
    assert "GCP banner" not in names  # consumable: counted on the stock page, not tagged
    assert ui.equipment.categories()[0] == {"value": "", "label": "All equipment"}
    assert ui.equipment.suggestTag("") == ""

    drone = register(ui, "Drone airframe", "SN-DR-001", make="IdeaForge", model="Q6", hours="42")
    register(ui, "Motor", "M-1")
    register(ui, "Tripod", "TP-1")
    assert ui.equipment.property("total") == 3
    assert drone["meters"] == "42 h" and drone["makeModel"] == "IdeaForge Q6"
    # A drone with no UIN or insurance needs attention.
    assert drone["complianceKind"] == "danger"
    assert ui.equipment.property("attentionCount") == 1

    ui.equipment.setSearch("idea")
    assert ui.equipment.property("count") == 1
    ui.equipment.setSearch("")
    ui.equipment.setCategory("drone_component")
    assert [r["tag"] for r in ui.equipment.model._rows] == ["MOT-0001"]
    ui.equipment.setCategory("")
    ui.equipment.setAttentionOnly(True)
    assert ui.equipment.property("count") == 1 and ui.equipment.property("attentionOnly")
    ui.equipment.setAttentionOnly(False)
    assert ui.equipment.property("count") == 3
    assert warnings_of(ui) == []


def test_register_and_edit_errors_are_shown(ui: UiContext) -> None:
    ui.equipment.register({"itemTypeId": "", "tag": "X"})
    assert "Choose what kind" in ui.equipment.property("error")
    ui.equipment.clearError()
    motor = item_type(ui, "Motor")
    ui.equipment.register({"itemTypeId": motor["value"], "tag": "MOT-0001"})
    settle(ui)
    assert "serial" in ui.equipment.property("error")
    ui.equipment.register({"itemTypeId": motor["value"], "tag": "MOT-0001", "serial": "M-1",
                           "hours": "lots"})  # fmt: skip
    settle(ui)
    assert "number" in ui.equipment.property("error")

    site = add_site(ui, "MAIN-STORE", "Main store")
    row = register(ui, "Motor", "M-1")
    detail = open_asset(ui, row["assetId"])
    ui.equipment.update(row["assetId"], detail["version"], {**detail, "tag": "MOT-0001",
                        "serial": "M-1B", "homeSiteId": site, "notes": "Spare"})  # fmt: skip
    settle(ui)
    detail = dict(ui.equipment.property("detail"))
    assert detail["serial"] == "M-1B" and detail["site"].startswith("MAIN-STORE")
    assert detail["notes"] == "Spare"
    ui.equipment.closeAsset()
    assert ui.equipment.property("detail") == {}


def test_asset_sheet_actions(ui: UiContext, tmp_path: Path) -> None:
    ui.shell.navigate("equipment")
    drone = register(ui, "Drone airframe", "SN-DR-001")
    motor = register(ui, "Motor", "M-1")
    battery = register(ui, "Drone flight battery", "B-1")
    sheet(ui, "AssetSheet").show(drone["assetId"])  # type: ignore[attr-defined]
    settle(ui, 300)
    detail = dict(ui.equipment.property("detail"))

    # Drones can hold UIN and insurance; a battery cannot.
    assert "uin" in [k["value"] for k in detail["documentKinds"]]
    assert "uin" not in [k["value"] for k in open_asset(ui, battery["assetId"])["documentKinds"]]
    detail = open_asset(ui, drone["assetId"])
    assert motor["assetId"] in [c["value"] for c in detail["looseComponents"]]

    # Fit and remove a part.
    ui.equipment.installComponent(drone["assetId"], "", "")
    assert "part" in ui.equipment.property("error")
    ui.equipment.installComponent(drone["assetId"], motor["assetId"], "Motor 1")
    settle(ui)
    detail = dict(ui.equipment.property("detail"))
    assert [c["tag"] for c in detail["components"]] == ["MOT-0001"]
    ui.equipment.removeComponent(motor["assetId"], "Bearing noise")
    settle(ui)
    assert dict(ui.equipment.property("detail"))["components"] == []

    # Documents, with a scan attached.
    scan = tmp_path / "uin.pdf"
    scan.write_bytes(b"%PDF-1.7\n% test scan\n")
    ui.equipment.addDocument(drone["assetId"], {"kind": "uin", "reference": "UA-123"},
                             QUrl.fromLocalFile(str(scan)).toString())  # fmt: skip
    ui.equipment.addDocument(drone["assetId"], {"kind": "insurance", "reference": "POL-9",
                             "validUntil": "2027-03-31"}, "")  # fmt: skip
    settle(ui)
    detail = dict(ui.equipment.property("detail"))
    assert {d["reference"] for d in detail["documents"]} == {"UA-123", "POL-9"}
    assert next(d for d in detail["documents"] if d["reference"] == "UA-123")["hasFile"]
    assert detail["problems"] == []
    insurance = next(d for d in detail["documents"] if d["reference"] == "POL-9")
    ui.equipment.removeDocument(insurance["documentId"], insurance["version"])
    settle(ui)
    assert len(dict(ui.equipment.property("detail"))["problems"]) == 1

    # Firmware.
    ui.equipment.recordFirmware(drone["assetId"], "v04.02.01", "", "")
    settle(ui)
    assert "date" in ui.equipment.property("error")
    ui.equipment.recordFirmware(drone["assetId"], "v04.02.01", "2026-11-01", "Before survey")
    settle(ui)
    assert dict(ui.equipment.property("detail"))["firmware"][0]["version"] == "v04.02.01"

    # Status: a reason is required to ground; returning to service is not.
    ui.equipment.changeStatus(drone["assetId"], "ground", " ")
    assert "reason" in ui.equipment.property("error")
    ui.equipment.changeStatus(drone["assetId"], "nonsense", "x")
    ui.equipment.changeStatus(drone["assetId"], "ground", "Arm cracked")
    settle(ui)
    detail = dict(ui.equipment.property("detail"))
    assert detail["serviceLabel"] == "Grounded" and detail["history"][0]["reason"] == "Arm cracked"
    assert "certify" in [a["key"] for a in detail["actions"]]
    ui.equipment.changeStatus(drone["assetId"], "certify", "")
    settle(ui)
    assert dict(ui.equipment.property("detail"))["serviceLabel"] == "Serviceable"
    assert warnings_of(ui) == []


def test_status_actions_respect_role() -> None:
    from ims.domain.assets.status import AssetStatus, Serviceability
    from ims.domain.identity.roles import Permission

    serviceable, grounded = AssetStatus(), AssetStatus(serviceability=Serviceability.UNSERVICEABLE)
    everything = frozenset(p.value for p in Permission)
    assert {"ground", "limit", "retire"} <= {
        a["key"] for a in available_actions(serviceable, everything)
    }
    assert "certify" not in [a["key"] for a in available_actions(serviceable, everything)]
    assert "certify" in [a["key"] for a in available_actions(grounded, everything)]
    reporter = frozenset({Permission.DEFECT_REPORT.value})
    assert [a["key"] for a in available_actions(serviceable, reporter)] == ["ground", "limit"]
    assert available_actions(grounded, reporter) == []


def test_print_labels(ui: UiContext, tmp_path: Path, no_external_viewer: list[str]) -> None:
    ui.equipment.printLabels([], QUrl.fromLocalFile(str(tmp_path / "none.pdf")).toString(), 0)
    assert "no assets" in ui.equipment.property("error")
    drone = register(ui, "Drone airframe", "SN-DR-001")
    register(ui, "Tripod", "TP-1")
    target = tmp_path / "labels"  # the .pdf suffix is added
    ui.equipment.printLabels([drone["assetId"]], QUrl.fromLocalFile(str(target)).toString(), 3)
    settle(ui)
    written = tmp_path / "labels.pdf"
    assert written.read_bytes().startswith(b"%PDF")
    assert no_external_viewer and no_external_viewer[0].endswith("labels.pdf")


# ---------------------------------------------------------------------- kits


def test_kits(ui: UiContext) -> None:
    ui.shell.navigate("equipment")
    site = add_site(ui, "MAIN-STORE", "Main store")
    drone = register(ui, "Drone airframe", "SN-DR-001")
    battery = register(ui, "Drone flight battery", "B-1")
    templates = ui.kits.templates()
    assert templates[0]["label"] == "No template"
    drone_kit = next(t for t in templates if t["label"] == "Drone kit")

    ui.kits.create({"code": "drone-01", "name": "Mapping kit 1", "templateId": drone_kit["value"],
                    "homeSiteId": site})  # fmt: skip
    ui.kits.create({"code": "spare", "name": "Loose spares"})
    settle(ui)
    assert ui.kits.property("count") == 2
    kit = ui.kits.model.find("code", "KIT-DRONE-01")
    assert kit["templateName"] == "Drone kit" and kit["statusKind"] == "warning"
    assert ui.kits.model.find("code", "KIT-SPARE")["statusLabel"] == "No template"

    sheet(ui, "KitSheet").show(kit["kitId"])  # type: ignore[attr-defined]
    settle(ui, 300)
    detail = dict(ui.kits.property("detail"))
    assert {c["value"] for c in detail["candidates"]} == {drone["assetId"], battery["assetId"]}
    ui.kits.addMember(kit["kitId"], detail["version"], drone["assetId"])
    settle(ui)
    detail = dict(ui.kits.property("detail"))
    assert [m["tag"] for m in detail["members"]] == ["DRN-0001"]
    assert not any("Drone airframe" in line for line in detail["missing"])
    assert open_asset(ui, drone["assetId"])["kitCode"] == "KIT-DRONE-01"

    # The same asset cannot go in a second kit.
    spare = ui.kits.model.find("code", "KIT-SPARE")
    ui.kits.addMember(spare["kitId"], spare["version"], drone["assetId"])
    settle(ui)
    assert ui.kits.property("error")
    ui.kits.clearError()
    ui.kits.addMember(spare["kitId"], spare["version"], "")  # nothing chosen: ignored

    ui.kits.openKit(kit["kitId"])
    settle(ui)
    detail = dict(ui.kits.property("detail"))
    ui.kits.removeMember(kit["kitId"], detail["version"], drone["assetId"])
    settle(ui)
    detail = dict(ui.kits.property("detail"))
    assert detail["members"] == []
    ui.kits.breakUp(kit["kitId"], detail["version"])
    settle(ui)
    assert ui.kits.property("count") == 1
    assert warnings_of(ui) == []


# ---------------------------------------------------------------------- stock


def test_gcp_stock(ui: UiContext) -> None:
    ui.shell.navigate("stock")
    settle(ui, 300)
    assert ui.stock.property("itemName") == "GCP banner"
    assert ui.stock.siteChoices() == []
    store = add_site(ui, "MAIN-STORE", "Main store")
    mine = add_site(ui, "KJR-MINE", "Keonjhar mine")
    ui.stock.refresh()
    settle(ui)
    assert {c["value"] for c in ui.stock.siteChoices()} == {store, mine}

    ui.stock.receive(store, "120", "PO-4411")
    ui.stock.receive(mine, "30", "Transfer")
    settle(ui)
    ui.stock.setReorderLevel(mine, "40")
    ui.stock.writeOff(store, "5", "Torn in storage")
    settle(ui)
    assert ui.stock.property("total") == 145
    assert ui.stock.property("lowCount") == 1
    rows = {r["siteId"]: r for r in ui.stock.sites._rows}
    assert rows[mine]["statusLabel"] == "Reorder" and rows[store]["statusLabel"] == "No level set"

    messages: list[str] = []
    ui.stock.saved.connect(messages.append)
    ui.stock.count(store, "112", "")
    settle(ui)
    ui.stock.count(store, "112", "")
    settle(ui)
    assert messages == ["Count recorded (-3)", "Count matches the records"]
    latest = ui.stock.movements._rows[0]
    assert latest["kind"] == "Count adjustment" and latest["quantity"] == "-3"
    assert latest["by"] == "Satya Upendra" and "115 on record" in latest["reason"]

    ui.stock.receive(store, "many", "")
    settle(ui)
    assert "whole number" in ui.stock.property("error")
    ui.stock.clearError()
    ui.stock.count(store, "-1", "")
    settle(ui)
    assert "negative" in ui.stock.property("error")
    ui.stock.clearError()
    ui.stock.writeOff(mine, "500", "Lost")
    settle(ui)
    assert ui.stock.property("error")
    assert warnings_of(ui) == []
