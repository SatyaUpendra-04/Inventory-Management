"""Batteries, calibration on the item sheet, and the alert centre, through the view-models."""

from __future__ import annotations

from typing import Any

import pytest

from ims.ui.app import UiContext
from tests.ui.conftest import settle, warnings_of
from tests.ui.test_operations_flow import World, sheet

pytestmark = pytest.mark.ui


@pytest.fixture
def world(ui: UiContext) -> World:
    return World(ui)


def battery(ui: UiContext, asset_id: str) -> dict[str, Any]:
    return dict(ui.batteries.model.find("assetId", asset_id))


def test_batteries_checks_limits_and_alerts(ui: UiContext, world: World) -> None:
    ui.equipment.register(
        {
            "itemTypeId": world.types["Drone flight battery"],
            "tag": "BAT-0050",
            "serial": "B-50",
            "cycles": "201",
        }
    )
    ui.equipment.register(
        {"itemTypeId": world.types["DGPS receiver battery"], "tag": "GBT-0050", "serial": "G-50"}
    )
    settle(ui)
    spent = ui.equipment.model.find("tag", "BAT-0050")["assetId"]
    receiver = ui.equipment.model.find("tag", "GBT-0050")["assetId"]
    ui.shell.navigate("batteries")
    settle(ui, 400)
    assert battery(ui, spent)["conditionLabel"] == "Retire"
    assert battery(ui, world.bat)["cyclesText"] == "0 / 200"
    ui.batteries.setFilter("attention")
    assert ui.batteries.property("attentionCount") >= 1
    assert all(r["condition"] != "ok" for r in ui.batteries.model._rows)
    ui.batteries.setFilter("all")
    ui.batteries.setSearch("gbt")
    assert [r["tag"] for r in ui.batteries.model._rows] == ["GBT-0050"]
    ui.batteries.setSearch("")

    # A check on the sheet.
    sheet(ui, "BatterySheet").show(world.bat)  # type: ignore[attr-defined]
    settle(ui, 300)
    ui.batteries.recordCheck(world.bat, {"health": "lots"})
    settle(ui)
    assert "whole number" in ui.batteries.property("error")
    ui.batteries.recordCheck(
        world.bat, {"health": "93", "resistance": "4.5", "imbalance": "7", "chargeState": "storage"}
    )
    settle(ui)
    detail = ui.batteries.property("detail")
    assert detail["health"] == "93%" and detail["checks"][0]["charge"] == "Storage charge"
    assert detail["isDroneBattery"] and detail["history"] == []
    ui.batteries.recordCheck(world.bat, {"swelling": True, "notes": "Puffed"})
    settle(ui)
    assert ui.batteries.property("detail")["conditionLabel"] == "Unsafe"
    ui.batteries.closeBattery()

    # Charge cycles on a receiver battery.
    ui.batteries.logCharge(receiver, "", "", "")
    settle(ui)
    assert "how many" in ui.batteries.property("error")
    ui.batteries.logCharge(receiver, "4", "", "Weekly charging")
    settle(ui)
    assert battery(ui, receiver)["cyclesText"] == "4 / 500"

    # Limits.
    policy = next(
        p for p in ui.batteries.property("policies") if p["type"] == "DGPS receiver battery"
    )
    ui.batteries.updatePolicy(policy["policyId"], policy["version"], {**policy, "cycleLimit": ""})
    settle(ui)
    assert "Enter the cycle limit" in ui.batteries.property("error")
    ui.batteries.updatePolicy(policy["policyId"], policy["version"], {**policy, "cycleLimit": "4"})
    settle(ui)
    assert battery(ui, receiver)["conditionLabel"] == "Retire"

    # The alert centre gathers it all; the bell opens it.
    ui.alerts.refresh()
    settle(ui)
    groups = {g["label"]: g for g in ui.alerts.property("groups")}
    assert "Batteries" in groups and ui.alerts.property("urgentCount") >= 3
    sheet(ui, "AlertsSheet").show()  # type: ignore[attr-defined]
    settle(ui, 300)
    assert warnings_of(ui) == []


def test_calibration_on_the_item_sheet(ui: UiContext, world: World) -> None:
    ui.shell.navigate("equipment")
    settle(ui, 300)
    sheet(ui, "AssetSheet").show(world.base)  # type: ignore[attr-defined]
    settle(ui, 300)
    detail = ui.equipment.property("detail")
    assert detail["tracksCalibration"] and detail["calibrations"] == []
    sheet(ui, "AssetSheet").startCalibration("verification")  # type: ignore[attr-defined]
    ui.equipment.recordCalibration(
        world.base,
        {
            "kind": "verification",
            "doneOn": "2026-11-07",
            "method": "RTK on control point",
            "reference": "GCP-07",
            "result": "fail",
            "horizontal": "12",
            "vertical": "70",
            "notes": "Vertical 7 cm out",
        },
        "",
    )
    settle(ui, 300)
    detail = ui.equipment.property("detail")
    row = detail["calibrations"][0]
    assert (row["kind"], row["result"], row["residual"]) == (
        "Verification",
        "Fail",
        "H 12 mm · V 70 mm",
    )
    assert detail["serviceLabel"] == "Grounded"
    assert "certify" not in [a["key"] for a in detail["actions"]]  # still grounded by the failure
    ui.equipment.recordCalibration(
        world.base,
        {
            "kind": "calibration",
            "doneOn": "",
            "method": "Lab",
            "reference": "Lab",
            "result": "pass",
        },
        "",
    )
    settle(ui)
    assert "date" in ui.equipment.property("error")
    ui.equipment.recordCalibration(
        world.base,
        {
            "kind": "calibration",
            "doneOn": "2026-11-08",
            "method": "Lab calibration",
            "reference": "Service centre",
            "result": "pass",
            "validUntil": "2027-11-08",
        },
        "",
    )
    settle(ui, 300)
    detail = ui.equipment.property("detail")
    assert detail["calibrations"][0]["validUntil"] == "08 Nov 2027"
    assert "certify" in [a["key"] for a in detail["actions"]]
    assert warnings_of(ui) == []
