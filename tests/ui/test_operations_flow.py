"""Projects, check-out, flight and survey logs, and returns, driven through the view-models
with the real QML loaded (so every page and sheet involved is checked for QML warnings)."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtCore import QObject

from ims.ui.app import UiContext
from ims.ui.viewmodels.projects import dates_text, hours_text, minutes_to_hours
from tests.ui.conftest import settle, warnings_of

pytestmark = pytest.mark.ui

PILOT = {
    "fullName": "Ravi Kumar", "username": "rkumar", "employeeId": "EMP-0102",
    "email": "ravi@example.com", "phone": "9123456780", "role": "pilot",
    "licenceNumber": "DGCA-RPC-2291", "licenceExpiry": "2027-12-20",
}  # fmt: skip
SURVEYOR = {
    "fullName": "Anita Das", "username": "adas", "employeeId": "EMP-0144",
    "email": "anita@example.com", "phone": "9000011122", "role": "surveyor",
}  # fmt: skip


def sheet(ui: UiContext, prefix: str) -> QObject:
    window = ui.engine.rootObjects()[0]
    found = next(
        (o for o in window.findChildren(QObject) if o.metaObject().className().startswith(prefix)),
        None,
    )
    assert found is not None, f"{prefix} not loaded"
    return found


class World:
    """Sites, crew, a compliant drone kit's worth of equipment and 120 GCP banners."""

    def __init__(self, ui: UiContext) -> None:
        self.ui = ui
        for code, name, kind in (("MAIN-STORE", "Main store", "store"),
                                 ("KJR-MINE", "Keonjhar mine", "mine_site")):  # fmt: skip
            ui.sites.create({"code": code, "name": name, "kind": kind, "status": "active"})
            settle(ui)
        self.passwords: dict[str, str] = {}
        ui.people.temporaryPassword.connect(
            lambda _name, user, password: self.passwords.__setitem__(user, password)
        )
        for person in (PILOT, SURVEYOR):
            ui.people.onboard(person)
            settle(ui)
        ui.equipment.refresh()
        ui.projects.refresh()
        settle(ui)
        self.store = ui.sites.model.find("code", "MAIN-STORE")["siteId"]
        self.mine = ui.sites.model.find("code", "KJR-MINE")["siteId"]
        self.types = {t["label"].split("  ·  ")[0]: t["value"] for t in ui.equipment.itemTypes()}
        self.drone = self.register("Drone airframe", "SN-1")
        self.bat = self.register("Drone flight battery", "B-1")
        self.sd = self.register("SD card", "")
        self.base = self.register("DGPS receiver (base / rover)", "R-1")
        self.rover = self.register("DGPS receiver (base / rover)", "R-2")
        self.tripod = self.register("Tripod", "")
        for kind, ref, until in (("uin", "UA-1", ""), ("insurance", "POL-1", "2027-06-30")):
            ui.equipment.addDocument(
                self.drone, {"kind": kind, "reference": ref, "validUntil": until}, ""
            )
        for receiver in (self.base, self.rover):
            ui.equipment.addDocument(
                receiver,
                {"kind": "calibration", "reference": "CAL", "validUntil": "2027-06-30"},
                "",
            )
        ui.stock.refresh()
        settle(ui)
        ui.stock.receive(self.store, "120", "PO-1")
        settle(ui)
        options = ui.projects.property("pilotOptions")
        self.pilot = next(o["value"] for o in options if o.get("name") == "Ravi Kumar")
        self.surveyor = next(
            o["value"]
            for o in ui.projects.property("surveyorOptions")
            if o.get("name") == "Anita Das"
        )

    def register(self, type_name: str, serial: str) -> str:
        ui = self.ui
        type_id = self.types[type_name]
        tag = ui.equipment.suggestTag(type_id)
        home = getattr(self, "store", "")
        ui.equipment.register(
            {"itemTypeId": type_id, "tag": tag, "serial": serial, "homeSiteId": home}
        )
        settle(ui)
        assert ui.equipment.property("error") == "", ui.equipment.property("error")
        return str(ui.equipment.model.find("tag", tag)["assetId"])

    @property
    def equipment(self) -> list[str]:
        return [self.drone, self.bat, self.sd, self.base, self.rover, self.tripod]


@pytest.fixture
def world(ui: UiContext) -> World:
    return World(ui)


def create_project(ui: UiContext, world: World) -> str:
    code = ui.projects.suggestCode(world.mine, "2026-11-08")
    ui.projects.create({"code": code, "name": "Pit survey", "siteId": world.mine,
                        "startsOn": "2026-11-08", "endsOn": "2026-11-20",
                        "chiefPilotId": world.pilot, "surveyorId": world.surveyor})  # fmt: skip
    settle(ui)
    assert ui.projects.property("error") == "", ui.projects.property("error")
    return str(ui.projects.model.find("code", code)["projectId"])


def test_formatting_helpers() -> None:
    from datetime import date
    from decimal import Decimal

    assert hours_text(Decimal("1.25")) == "1 h 15 min" and hours_text(Decimal("0.75")) == "45 min"
    assert minutes_to_hours("45") == Decimal("0.75") and minutes_to_hours("38") == Decimal("0.63")
    assert dates_text(date(2026, 11, 8), None) == "From 08 Nov 2026"
    assert dates_text(date(2026, 12, 28), date(2027, 1, 4)).startswith("28 Dec 2026")


def test_project_cycle_through_the_screens(ui: UiContext, world: World) -> None:
    ui.shell.navigate("projects")
    settle(ui, 300)
    assert ui.projects.suggestCode(world.mine, "2026-11-08") == "PRJ-KJR-2611"
    sheet(ui, "ProjectFormSheet").openNew()  # type: ignore[attr-defined]
    settle(ui, 300)
    ui.projects.create({"code": "", "name": "x", "siteId": "", "startsOn": "2026-11-08"})
    settle(ui)
    assert "site" in ui.projects.property("error")
    sheet(ui, "ProjectFormSheet").close()  # type: ignore[attr-defined]
    project = create_project(ui, world)
    row = ui.projects.model.find("projectId", project)
    assert row["statusLabel"] == "Planned" and row["chiefPilot"] == "Ravi Kumar"
    ui.projects.setFilter("completed")
    assert ui.projects.property("count") == 0
    ui.projects.setFilter("open")
    ui.projects.setSearch("pit")
    assert ui.projects.property("count") == 1
    ui.projects.setSearch("")

    # Check out: the readiness check blocks a crew without the pilot, then passes.
    sheet(ui, "ProjectSheet").show(project)  # type: ignore[attr-defined]
    settle(ui, 300)
    sheet(ui, "CheckoutSheet").openFor(project)  # type: ignore[attr-defined]
    settle(ui, 300)
    choices = ui.deployments.property("choices")
    assert {e["value"] for e in choices["equipment"]} >= set(world.equipment)
    draft: dict[str, Any] = {"projectId": project, "assetIds": world.equipment,
                             "crewIds": [world.surveyor], "gcpQuantity": "20",
                             "gcpSiteId": world.store, "deployedOn": "2026-11-08"}  # fmt: skip
    ui.deployments.check(draft)
    settle(ui)
    readiness = ui.deployments.property("readiness")
    assert not readiness["ready"] and any("DGCA" in b for b in readiness["blockers"])
    draft["crewIds"] = [world.pilot, world.surveyor]
    ui.deployments.check({**draft, "gcpQuantity": "lots"})
    settle(ui)
    assert "whole number" in ui.deployments.property("readiness")["blockers"][0]
    ui.deployments.check(draft)
    settle(ui)
    assert ui.deployments.property("readiness")["ready"]
    ui.deployments.deploy(draft)
    settle(ui, 300)
    assert ui.deployments.property("error") == ""
    sheet(ui, "CheckoutSheet").close()  # type: ignore[attr-defined]
    ui.deployments.deploy({**draft, "projectId": ""})
    settle(ui)
    assert "project" in ui.deployments.property("error")
    ui.deployments.clearError()

    # Logs.
    ui.projects.openProject(project)
    settle(ui)
    detail = ui.projects.property("detail")
    assert detail["statusLabel"] == "Active" and detail["totals"]["gcpIssued"] == 20
    out = detail["loggable"][0]
    assert [d["value"] for d in out["drones"]] == [world.drone]
    sheet(ui, "SortieSheet").start(detail["loggable"])  # type: ignore[attr-defined]
    sheet(ui, "SurveySheet").start(detail["loggable"])  # type: ignore[attr-defined]
    settle(ui, 300)
    flight = {"deploymentId": out["deploymentId"], "droneId": world.drone, "pilotId": world.pilot,
              "flownOn": "2026-11-08", "minutes": "45", "batteryIds": [world.bat],
              "mediaIds": [world.sd]}  # fmt: skip
    ui.projects.logSortie({**flight, "minutes": "soon"})
    settle(ui)
    assert "minutes" in ui.projects.property("error")
    ui.projects.logSortie(flight)
    settle(ui)
    ui.projects.logSortie({**flight, "minutes": "30", "ppkBaseId": world.base, "batteryIds": []})
    settle(ui)
    ui.projects.logSession({"deploymentId": out["deploymentId"], "surveyorId": world.surveyor,
                            "surveyedOn": "2026-11-08", "mode": "ppk", "baseId": world.base,
                            "roverIds": [world.rover], "hours": "3.5", "area": "42.5",
                            "points": "380", "fixRate": "97.5"})  # fmt: skip
    settle(ui)
    ui.projects.logSession({"deploymentId": out["deploymentId"], "surveyorId": world.surveyor,
                            "rover": [], "hours": ""})  # fmt: skip
    settle(ui)
    assert "hours" in ui.projects.property("error")
    detail = ui.projects.property("detail")
    assert detail["totals"]["flights"] == 2 and detail["totals"]["flightTime"] == "1 h 15 min"
    assert detail["sessions"][0]["fixRate"] == "97.5%"
    newest = next(f for f in detail["sorties"] if f["time"] == "30 min")
    ui.projects.voidSortie(newest["sortieId"], newest["version"], "Logged twice")
    settle(ui)
    detail = ui.projects.property("detail")
    assert [f["void"] for f in detail["sorties"] if f["time"] == "30 min"] == [True]
    assert detail["totals"]["flights"] == 1
    session = detail["sessions"][0]
    ui.projects.voidSession(session["sessionId"], session["version"], "Wrong receiver")
    settle(ui)
    assert ui.projects.property("detail")["sessions"][0]["void"]
    drone_row = ui.equipment.model.find("assetId", world.drone)
    assert drone_row["meters"] == "0.75 h · 1 cycle"

    # Return: tripod comes back with a defect; 14 banners back, 6 used.
    sheet(ui, "ReturnSheet").show(out["deploymentId"])  # type: ignore[attr-defined]
    settle(ui, 300)
    back = ui.deployments.property("detail")
    assert back["canReturn"] and back["gcp"] == 20
    lines = [{"assetId": i["assetId"], "condition": "ok"} for i in back["items"]]
    tripod_line = next(line for line in lines if line["assetId"] == world.tripod)
    tripod_line.update(condition="limited")
    ui.deployments.returnEquipment(back["deploymentId"], back["version"],
                                   {"lines": lines, "gcpIssued": "20", "gcpReturned": "14",
                                    "returnSiteId": world.store})  # fmt: skip
    settle(ui)
    assert "Describe the defect" in ui.deployments.property("error")
    tripod_line.update(note="Leg clamp loose")
    ui.deployments.returnEquipment(back["deploymentId"], back["version"],
                                   {"lines": lines, "gcpIssued": "20", "gcpReturned": "14",
                                    "returnSiteId": world.store})  # fmt: skip
    settle(ui, 300)
    assert ui.deployments.property("error") == ""
    assert ui.equipment.model.find("assetId", world.tripod)["serviceLabel"] == "Limited"
    assert ui.stock.property("total") == 114
    ui.deployments.openDeployment(out["deploymentId"])
    settle(ui)
    assert ui.deployments.property("detail")["gcpConsumed"] == 6

    # Lists, status and removal.
    ui.shell.navigate("deployments")
    settle(ui, 300)
    assert ui.deployments.property("count") == 0 and ui.deployments.property("outCount") == 0
    ui.deployments.setFilter("all")
    assert ui.deployments.property("count") == 1
    ui.projects.openProject(project)
    settle(ui)
    detail = ui.projects.property("detail")
    assert {a["value"] for a in detail["statusActions"]} == {"completed"}
    ui.projects.setStatus(project, detail["version"], "completed")
    settle(ui)
    assert ui.projects.property("detail")["statusLabel"] == "Completed"
    spare = create_project(ui, world)
    ui.projects.openProject(spare)
    settle(ui)
    assert ui.projects.property("detail")["canRemove"]
    ui.projects.update(spare, 1, {"code": "PRJ-KJR-2611-2", "name": "Renamed", "siteId": world.mine,
                                  "startsOn": "2026-11-09"})  # fmt: skip
    settle(ui)
    assert ui.projects.property("detail")["name"] == "Renamed"
    ui.projects.remove(spare, 2)
    settle(ui)
    assert ui.projects.property("total") == 1
    assert warnings_of(ui) == []


def test_pilots_see_their_assigned_and_completed_projects(
    ui: UiContext, world: World, picture: str
) -> None:
    named = create_project(ui, world)
    finished = create_project(ui, world)
    ui.projects.create({"code": "PRJ-OTHER-1", "name": "Someone else's", "siteId": world.mine,
                        "startsOn": "2026-11-08"})  # fmt: skip
    settle(ui)
    for version, status in ((1, "active"), (2, "completed")):
        ui.projects.setStatus(finished, version, status)
        settle(ui)
    assert ui.projects.property("crewView") is False
    assert [o["value"] for o in ui.projects.property("filterOptions")] == [
        "open",
        "completed",
        "cancelled",
        "all",
    ]

    # Sign in as the pilot.
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
    assert ui.session.stage == "app"
    ui.shell.navigate("projects")
    settle(ui, 300)

    assert ui.projects.property("crewView") is True
    assert [o["label"] for o in ui.projects.property("filterOptions")] == [
        "Assigned 1",
        "Completed 1",
        "All",
    ]
    assert ui.projects.property("filter") == "assigned"
    assert [r["projectId"] for r in ui.projects.model._rows] == [named]
    row = ui.projects.model._rows[0]
    assert row["myRole"] == "Chief pilot" and row["myWork"] == ""
    ui.projects.setFilter("completed")
    assert [r["projectId"] for r in ui.projects.model._rows] == [finished]
    ui.projects.setFilter("all")
    assert ui.projects.property("count") == 3
    ui.projects.openProject(named)
    settle(ui)
    assert ui.projects.property("detail")["myRole"] == "Chief pilot"
    assert warnings_of(ui) == []
