"""The gates before the app, and People / Sites administration, driven through the view-models
with the real QML loaded (so every screen involved is also checked for QML warnings)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject

from ims.ui.app import Services, UiContext
from tests.ui.conftest import ADMIN, ADMIN_PASSWORD, settle, sign_up_admin, warnings_of

pytestmark = pytest.mark.ui

PILOT = {
    "fullName": "Ravi Kumar", "username": "rkumar", "employeeId": "EMP-0102",
    "email": "ravi@example.com", "phone": "9123456780", "role": "pilot",
    "licenceNumber": "DGCA-RPC-2291", "licenceExpiry": "2027-06-30",
}  # fmt: skip


def gate_source(ui: UiContext) -> str:
    gate = ui.engine.rootObjects()[0].findChild(QObject, "gate")
    assert gate is not None
    return str(gate.property("source").toString()) if gate.property("active") else ""


def onboard(ui: UiContext, values: dict[str, str]) -> str:
    issued: dict[str, str] = {}
    ui.people.temporaryPassword.connect(lambda _n, _u, pw: issued.setdefault("pw", pw))
    ui.people.onboard(values)
    settle(ui, 200)
    assert ui.people.property("error") == "", ui.people.property("error")
    return issued["pw"]


def test_first_run_shows_setup_then_profile_then_app(fresh_ui: UiContext, picture: str) -> None:
    ui = fresh_ui
    assert ui.session.stage == "setup" and gate_source(ui).endswith("SetupPage.qml")
    ui.session.setupAdmin({**ADMIN, "username": "x"}, ADMIN_PASSWORD, ADMIN_PASSWORD)
    settle(ui)
    assert ui.session.stage == "setup" and "username" in ui.session.error.lower()
    sign_up_admin(ui, picture)
    assert gate_source(ui) == "" and ui.session.isAdmin
    assert ui.session.displayName == "Satya Upendra" and ui.session.initials == "SU"
    assert ui.session.picture.startswith("image://files/")
    assert "people" in [s["key"] for s in ui.shell.sections]
    assert warnings_of(ui) == []


def test_new_pilot_signs_in_changes_password_and_adds_picture(ui: UiContext, picture: str) -> None:
    temporary = onboard(ui, PILOT)
    ui.session.signOut()
    settle(ui)
    assert ui.session.stage == "signIn" and gate_source(ui).endswith("LoginPage.qml")

    ui.session.signIn("rkumar", "wrong")
    settle(ui)
    assert ui.session.error == "The username or password is not correct."
    ui.session.signIn("", "")
    assert ui.session.error == "Enter your username and password."

    ui.session.signIn("rkumar", temporary)
    settle(ui)
    assert ui.session.stage == "changePassword" and gate_source(ui).endswith(
        "ChangePasswordPage.qml"
    )
    ui.session.changePassword(temporary, "Ravi-Survey-2026!", "Ravi-Survey-2026!")
    settle(ui)
    assert ui.session.stage == "completeProfile"
    ui.session.finishProfile()
    assert ui.session.error == "Add a profile picture to continue."
    ui.session.uploadPicture(picture)
    settle(ui)
    ui.session.finishProfile()
    settle(ui)
    assert ui.session.stage == "app" and ui.session.roleLabel == "Pilot"
    assert ui.session.licence["number"] == "DGCA-RPC-2291"
    keys = [s["key"] for s in ui.shell.sections]
    assert "people" not in keys and "sites" in keys
    assert warnings_of(ui) == []


def test_password_checklist_reports_each_rule(ui: UiContext) -> None:
    items = ui.session.passwordChecklist("Short", "satya")  # mixed case, nothing else
    assert [i["met"] for i in items] == [False, True, False, False, True]
    lower_only = ui.session.passwordChecklist("short", "satya")
    assert [i["met"] for i in lower_only] == [False, False, False, False, True]
    assert all(i["met"] for i in ui.session.passwordChecklist("Field-Survey-2026!", "satya"))


def test_people_admin_actions(ui: UiContext, services: Services) -> None:
    onboard(ui, PILOT)
    ravi = ui.people.model.find("username", "rkumar")
    assert ravi["accountLabel"] == "Awaiting first sign-in" and ravi["licenceStatus"] == "valid"

    ui.people.setFilterText("ravi")
    assert ui.people.property("count") == 1
    ui.people.setFilterText("")
    ui.people.setRoleFilter("admin")
    assert ui.people.property("count") == 1
    ui.people.setRoleFilter("")

    ui.people.update(ravi["personId"], ravi["version"], {**PILOT, "phone": "9000000000"})
    settle(ui)
    assert ui.people.person(ravi["personId"])["phone"] == "9000000000"

    reset: dict[str, str] = {}
    ui.people.temporaryPassword.connect(lambda _n, user, _pw: reset.setdefault("user", user))
    ui.people.resetPassword(ravi["personId"])
    settle(ui)
    assert reset == {"user": "rkumar"}

    for _ in range(5):  # someone keeps typing the wrong password
        services.accounts.sign_in("rkumar", "wrong")
    ui.people.refresh()
    settle(ui)
    assert ui.people.person(ravi["personId"])["accountLabel"] == "Locked"
    ui.people.unlock(ravi["personId"])
    settle(ui)
    assert ui.people.person(ravi["personId"])["accountLabel"] == "Awaiting first sign-in"

    current = ui.people.person(ravi["personId"])
    ui.people.setActive(ravi["personId"], current["version"], False)
    settle(ui)
    assert ui.people.person(ravi["personId"])["accountLabel"] == "Deactivated"
    current = ui.people.person(ravi["personId"])
    ui.people.setActive(ravi["personId"], current["version"], True)
    settle(ui)
    current = ui.people.person(ravi["personId"])
    ui.people.remove(ravi["personId"], current["version"])
    settle(ui)
    assert ui.people.property("total") == 1
    assert [r["value"] for r in ui.people.roles()] == ["admin", "pilot", "surveyor"]
    assert warnings_of(ui) == []


def test_people_errors_are_shown_not_raised(ui: UiContext) -> None:
    ui.people.onboard({**PILOT, "licenceNumber": "", "licenceExpiry": ""})
    settle(ui)
    assert "DGCA" in ui.people.property("error")
    ui.people.clearError()
    assert ui.people.property("error") == ""
    ui.people.onboard({**PILOT, "licenceExpiry": "not-a-date"})
    settle(ui)
    assert "valid date" in ui.people.property("error")


def test_sites_admin(ui: UiContext) -> None:
    assert ui.sites.property("canManage")
    ui.sites.create({"code": "kjr-mine", "name": "Keonjhar mine", "kind": "mine_site",
                     "status": "planned", "area": "1,250.5"})  # fmt: skip
    settle(ui)
    assert ui.sites.property("count") == 1
    row = ui.sites.model.find("code", "KJR-MINE")
    assert (
        row["kindLabel"] == "Mine site"
        and row["area"] == "1250.5"
        and row["statusLabel"] == "Planned"
    )
    ui.sites.update(row["siteId"], row["version"], {**row, "latitude": "21.6", "longitude": "85.5",
                                                     "area": ""})  # fmt: skip
    settle(ui)
    assert ui.sites.site(row["siteId"])["coordinates"] == "21.6000, 85.5000"
    ui.sites.create({"code": "x", "name": "Bad", "latitude": "north"})
    settle(ui)
    assert "number" in ui.sites.property("error")
    current = ui.sites.site(row["siteId"])
    ui.sites.remove(row["siteId"], current["version"])
    settle(ui)
    assert ui.sites.property("count") == 0
    assert next(k["value"] for k in ui.sites.kinds()) == "store"
    assert len(ui.sites.statuses()) == 3
