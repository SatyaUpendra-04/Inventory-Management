"""Maintenance screens driven through the view-model with the real QML loaded."""

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


def row(rows: list[dict[str, Any]], **match: Any) -> dict[str, Any]:
    return next(r for r in rows if all(r[k] == v for k, v in match.items()))


def test_due_defects_work_orders_and_programme(ui: UiContext, world: World) -> None:
    worn = world.register("Motor", "M-OLD")  # registered after sign-in: programme is installed
    ui.equipment.register({"itemTypeId": world.types["Drone airframe"], "tag": "DRN-0050",
                           "serial": "SN-50", "hours": "57"})  # fmt: skip
    settle(ui)
    tired = ui.equipment.model.find("tag", "DRN-0050")["assetId"]
    ui.shell.navigate("maintenance")
    settle(ui, 400)
    due = ui.maintenance.property("due")
    inspection = row(due, tag="DRN-0050", task="Routine inspection")
    assert inspection["stateLabel"] == "Overdue" and inspection["summary"] == "7 h over"
    assert ui.maintenance.property("overdueCount") >= 1
    assert worn  # a new motor has nothing due yet
    labels = [g["itemType"] for g in ui.maintenance.property("programme")]
    assert "Drone airframe" in labels and "Motor" in labels

    # Opening the page grounded the overdue drone.
    ui.equipment.refresh()
    settle(ui)
    assert ui.equipment.model.find("assetId", tired)["serviceLabel"] == "Grounded"

    # Report and assess a defect from the asset sheet.
    ui.shell.navigate("equipment")
    settle(ui, 300)
    sheet(ui, "AssetSheet").show(world.drone)  # type: ignore[attr-defined]
    settle(ui, 300)
    maintenance = ui.equipment.property("detail")["maintenance"]
    assert {t["task"] for t in maintenance["tasks"]} == {"Routine inspection", "Annual service"}
    ui.maintenance.reportDefect(world.drone, "Arm 3 creaks", False)
    settle(ui, 300)
    assert ui.equipment.property("detail")["maintenance"]["defects"][0]["stateLabel"] == "To assess"
    defect = row(ui.maintenance.property("defects"), tag="DRN-0001")
    assert defect["canAssess"]
    ui.shell.navigate("maintenance")
    settle(ui, 300)
    sheet(ui, "DefectSheet").show(defect)  # type: ignore[attr-defined]
    ui.maintenance.assessDefect(defect["defectId"], defect["version"], "deferred", "", "", "")
    settle(ui)
    assert "limitation" in ui.maintenance.property("error")
    ui.maintenance.assessDefect(defect["defectId"], defect["version"], "deferred",
                                "Max wind 8 m/s", "2026-11-20", "")  # fmt: skip
    settle(ui)
    assert row(ui.maintenance.property("defects"), tag="DRN-0001")["stateLabel"] == "Deferred"

    # Work order on the grounded drone: open, start, complete, sign off.
    sheet(ui, "WorkOrderSheet").openNew(tired, "DRN-0050", "Inspection",  # type: ignore[attr-defined]
                                        [inspection["taskId"]], [])  # fmt: skip
    settle(ui, 300)
    ui.maintenance.openWorkOrder(tired, "50 h inspection", [inspection["taskId"]], [])
    settle(ui, 300)
    order = row(ui.maintenance.property("orders"), tag="DRN-0050")
    assert order["stateLabel"] == "Open" and ui.maintenance.property("openOrders") == 1
    ui.maintenance.openOrder(order["workOrderId"])
    settle(ui)
    detail = ui.maintenance.property("order")
    assert [m["value"] for m in detail["moves"]] == ["in_progress", "cancelled"]
    ui.maintenance.moveOrder(detail["workOrderId"], detail["version"], "in_progress", "")
    settle(ui)
    detail = ui.maintenance.property("order")
    assert detail["canComplete"]
    ui.maintenance.completeOrder(detail["workOrderId"], detail["version"], "Checked", "")
    settle(ui)
    detail = ui.maintenance.property("order")
    assert detail["canCertify"] and detail["blockers"] == []
    ui.maintenance.certify(detail["workOrderId"], detail["version"])
    settle(ui)
    assert ui.maintenance.property("order")["stateLabel"] == "Returned to service"
    ui.maintenance.closeOrder()
    ui.equipment.refresh()
    settle(ui)
    assert ui.equipment.model.find("assetId", tired)["serviceLabel"] == "Serviceable"

    # Programme: add and edit a task.
    tripod_type = next(t["value"] for t in ui.maintenance.itemTypes() if t["label"] == "Tripod")
    sheet(ui, "TaskSheet").openNew()  # type: ignore[attr-defined]
    ui.maintenance.addTask({"itemTypeId": tripod_type, "name": "Leg lock check", "everyDays": "x"})
    settle(ui)
    assert "whole number" in ui.maintenance.property("error")
    ui.maintenance.addTask({"itemTypeId": tripod_type, "name": "Leg lock check", "everyDays": "60"})
    settle(ui)
    tripod_tasks = row(ui.maintenance.property("programme"), itemType="Tripod")["tasks"]
    task = tripod_tasks[0]
    assert task["intervals"] == "Every 60 days"
    ui.maintenance.updateTask(task["taskId"], task["version"], {**task, "name": "Leg locks",
                              "everyDays": "45", "toleranceDays": "5"})  # fmt: skip
    settle(ui)
    task = row(ui.maintenance.property("programme"), itemType="Tripod")["tasks"][0]
    assert (task["name"], task["tolerance"]) == ("Leg locks", "+5 days")
    ui.maintenance.recordDone(world.tripod, task["taskId"], "2026-11-01", "Done at the store")
    settle(ui)
    assert ui.maintenance.property("error") == ""
    assert warnings_of(ui) == []


def test_crew_report_but_do_not_manage(ui: UiContext, world: World, picture: str) -> None:
    ui.session.signOut()
    settle(ui)
    ui.session.signIn("rkumar", world.passwords["rkumar"])
    settle(ui)
    ui.session.changePassword(world.passwords["rkumar"], "Ravi-Survey-2026!", "Ravi-Survey-2026!")
    settle(ui)
    ui.session.uploadPicture(picture)
    settle(ui)
    ui.session.finishProfile()
    settle(ui, 300)
    assert ui.maintenance.property("canReport") and not ui.maintenance.property("canManage")
    ui.shell.navigate("maintenance")
    settle(ui, 300)
    ui.maintenance.reportDefect(world.tripod, "Head wobbles", True)
    settle(ui)
    defect = row(ui.maintenance.property("defects"), tag="TRP-0001")
    assert defect["stateLabel"] == "Grounding" and not defect["canAssess"]
    assert warnings_of(ui) == []
