"""Reservations, calendar, check-out from a booking, and the stocktake, driven through the
view-models with the real QML loaded (so every page and sheet is checked for warnings)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from PySide6.QtCore import QObject

from ims.application.context import Actor, CommandContext
from ims.domain.common.ids import new_command_id
from ims.ui.app import UiContext
from tests.ui.conftest import settle, warnings_of
from tests.ui.test_operations_flow import World, create_project, sheet

pytestmark = pytest.mark.ui

TODAY = date(2026, 11, 8)  # the test clock


def iso(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


@pytest.fixture
def world(ui: UiContext) -> World:
    return World(ui)


def test_book_review_calendar_and_check_out(ui: UiContext, world: World) -> None:
    project = create_project(ui, world)
    ui.shell.navigate("reservations")
    settle(ui, 300)
    assert ui.reservations.property("canApprove") and ui.reservations.property("count") == 0

    # Request sheet with a live conflict check.
    sheet(ui, "ReservationSheet").openNew(project)  # type: ignore[attr-defined]
    settle(ui, 300)
    assert ui.deployments.property("choices")["bookable"]
    draft: dict[str, Any] = {"projectId": project, "startsOn": iso(2), "endsOn": iso(6),
                             "assetIds": [world.drone, world.bat], "gcpQuantity": "20",
                             "gcpSiteId": world.store}  # fmt: skip
    ui.reservations.check({**draft, "startsOn": ""})
    settle(ui)
    assert "Choose the first and last day" in ui.reservations.property("conflicts")["blockers"][0]
    ui.reservations.check({**draft, "gcpQuantity": "lots"})
    settle(ui)
    assert "whole number" in ui.reservations.property("conflicts")["blockers"][0]
    ui.reservations.check(draft)
    settle(ui)
    assert ui.reservations.property("conflicts")["ready"]
    ui.reservations.request({**draft, "projectId": ""})
    settle(ui)
    assert "project" in ui.reservations.property("error")
    ui.reservations.request(draft)  # an administrator's booking is confirmed straight away
    settle(ui, 300)
    assert ui.reservations.property("error") == ""
    ui.reservations.setFilter("upcoming")
    row = ui.reservations.model._rows[0]
    assert row["statusLabel"] == "Booked" and row["mine"] and row["gcp"] == 20
    labels = [o["label"] for o in ui.reservations.property("filterOptions")]
    assert labels == ["Waiting", "Booked 1", "All"]

    # A second project cannot take the same drone on those days.
    other = create_project(ui, world)
    ui.reservations.check({**draft, "projectId": other, "assetIds": [world.drone]})
    settle(ui)
    assert "already booked" in ui.reservations.property("conflicts")["blockers"][0]

    # Review sheet and calendar.
    rid = row["reservationId"]
    sheet(ui, "ReservationSheet").show(rid)  # type: ignore[attr-defined]
    settle(ui, 300)
    detail = ui.reservations.property("detail")
    assert detail["canCheckOut"] and detail["canCancel"] and not detail["canApprove"]
    assert {i["assetId"] for i in detail["items"]} == {world.drone, world.bat}
    calendar = ui.reservations.property("calendar")
    assert len(calendar["days"]) == 28 and calendar["days"][calendar_today(calendar)]["today"]
    assert {r["label"] for r in calendar["assets"]} >= {"DRN-0001", "BAT-0001"}
    assert calendar["projects"][0]["bars"][0]["label"] == "Booked · 2 items"
    ui.reservations.shiftCalendar(1)
    settle(ui)
    assert ui.reservations.property("calendar")["start"] != calendar["start"]
    ui.reservations.calendarToday()
    settle(ui)
    assert ui.reservations.property("calendar")["start"] == calendar["start"]

    # Check out from the booking: the reservation is fulfilled.
    sheet(ui, "CheckoutSheet").openFromReservation(detail)  # type: ignore[attr-defined]
    settle(ui, 300)
    ui.deployments.deploy({"projectId": project, "assetIds": detail["extraAssetIds"],
                           "crewIds": [world.pilot], "gcpQuantity": "20",
                           "gcpSiteId": world.store, "reservationId": rid})  # fmt: skip
    settle(ui, 300)
    assert ui.deployments.property("error") == ""
    ui.reservations.openReservation(rid)
    settle(ui)
    assert ui.reservations.property("detail")["statusLabel"] == "Checked out"
    ui.projects.openProject(project)
    settle(ui)
    assert ui.projects.property("detail")["reservations"][0]["statusLabel"] == "Checked out"
    assert warnings_of(ui) == []


def calendar_today(calendar: dict[str, Any]) -> int:
    return next(i for i, d in enumerate(calendar["days"]) if d["today"])


def test_requests_wait_for_approval_and_can_be_rejected(ui: UiContext, world: World) -> None:
    """Approve, reject and cancel through the view-model (requests by crew are covered in
    the application tests; here an administrator reviews them)."""
    project = create_project(ui, world)
    pilot = next(u for u in ui_services(ui).users.list_users(ui.session.actor())
                 if u.username == "rkumar")  # fmt: skip
    for days in (2, 10):
        ui_services(ui).reservations.request(
            CommandContext(new_command_id(), Actor.from_user(pilot)),
            project_id=uuid.UUID(project), starts_on=TODAY + timedelta(days=days),
            ends_on=TODAY + timedelta(days=days + 2), asset_ids=[uuid.UUID(world.tripod)],
        )  # fmt: skip
    ui.shell.navigate("reservations")
    settle(ui, 300)
    ui.reservations.refresh()
    settle(ui)
    assert ui.reservations.property("pendingCount") == 2
    first, second = ui.reservations.model._rows
    assert not first["mine"] and first["requestedBy"] == "Ravi Kumar"
    sheet(ui, "ReservationSheet").show(first["reservationId"])  # type: ignore[attr-defined]
    settle(ui, 300)
    assert ui.reservations.property("detail")["canApprove"]
    ui.reservations.approve(first["reservationId"], first["version"], "Fine")
    settle(ui)
    ui.reservations.reject(second["reservationId"], second["version"], "")
    settle(ui)
    assert "reason" in ui.reservations.property("error")
    ui.reservations.reject(second["reservationId"], second["version"], "Tripod in use")
    settle(ui)
    ui.reservations.setFilter("all")
    statuses = {r["reservationId"]: r["statusLabel"] for r in ui.reservations.model._rows}
    assert statuses == {first["reservationId"]: "Booked", second["reservationId"]: "Rejected"}
    ui.reservations.cancel(first["reservationId"], 2, "Job moved")
    settle(ui)
    ui.reservations.openReservation(first["reservationId"])
    settle(ui)
    assert ui.reservations.property("detail")["statusLabel"] == "Cancelled"
    ui.reservations.closeReservation()
    assert ui.reservations.property("detail") == {}
    assert warnings_of(ui) == []


def test_stock_booked_and_stocktake(ui: UiContext, world: World) -> None:
    project = create_project(ui, world)
    ui.stock.setReorderLevel(world.store, "100")
    settle(ui)
    ui.reservations.request({"projectId": project, "startsOn": iso(2), "endsOn": iso(4),
                             "gcpQuantity": "30", "gcpSiteId": world.store})  # fmt: skip
    settle(ui, 300)
    ui.shell.navigate("stock")
    settle(ui, 300)
    row = ui.stock.sites._rows[0]
    assert (row["onHand"], row["booked"], row["free"]) == (120, 30, 90)
    assert row["statusLabel"] == "Bookings go below level"
    stocktake = ui.engine.rootObjects()[0].findChild(QObject, "stocktakeSheet")
    assert stocktake is not None
    stocktake.start()  # type: ignore[attr-defined]
    settle(ui, 300)
    ui.stock.stocktake({world.store: "117", world.mine: ""}, "Quarter end")
    settle(ui, 300)
    assert ui.stock.property("variance") == [
        {"site": "MAIN-STORE · Main store", "expected": 120, "counted": 117, "variance": "-3",
         "kind": "warning"}
    ]  # fmt: skip
    ui.stock.stocktake({world.store: "x"}, "")
    settle(ui)
    assert "whole number" in ui.stock.property("error")
    ui.stock.clearVariance()
    assert ui.stock.property("variance") == []
    assert warnings_of(ui) == []


def ui_services(ui: UiContext) -> Any:
    """The services behind the view-models (the same instance the test fixture built)."""
    return ui.reservations._sv
