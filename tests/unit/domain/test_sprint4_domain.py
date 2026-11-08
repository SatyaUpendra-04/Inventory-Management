"""Rules added in Sprint 4: configuration history, compliance documents, firmware and kits."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from ims.domain.assets.catalogue import DEFAULT_CATALOGUE
from ims.domain.assets.configuration import (
    ConfigChange,
    ConfigEvent,
    Placement,
    check_install,
    current_placement,
)
from ims.domain.assets.documents import (
    AssetDocument,
    DocumentKind,
    allowed_kinds,
    check_document_for_type,
    compliance_problems,
)
from ims.domain.assets.firmware import FirmwareRecord, check_new_firmware, current_version
from ims.domain.assets.status import AssetStatus, Serviceability
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import (
    AssetId,
    CommandId,
    DocumentId,
    EntryId,
    KitId,
    KitTemplateId,
    UserId,
    uuid7,
)
from ims.domain.kits import (
    DEFAULT_TEMPLATES,
    Kit,
    KitTemplate,
    TemplateLine,
    check_member,
    completeness,
)

T = {t.code: t for t in DEFAULT_CATALOGUE}
NOW = datetime(2026, 11, 8, 6, 30, tzinfo=UTC)
DRONE, MOTOR = AssetId(uuid7()), AssetId(uuid7())


def event(sequence: int, change: ConfigChange, parent: AssetId = DRONE) -> ConfigEvent:
    return ConfigEvent(
        id=EntryId(uuid7()), component_id=MOTOR, sequence=sequence, change=change,
        parent_id=parent, position="Motor 1", recorded_at=NOW, recorded_by=UserId(uuid7()),
        command_id=CommandId(uuid7()),
    )  # fmt: skip


class TestConfiguration:
    def test_placement_follows_the_history(self) -> None:
        assert current_placement([]) is None
        installed = [event(1, ConfigChange.INSTALLED)]
        assert current_placement(installed) == Placement(DRONE, "Motor 1")
        assert current_placement([*installed, event(2, ConfigChange.REMOVED)]) is None

    @pytest.mark.parametrize(
        "history",
        [
            [(2, ConfigChange.INSTALLED)],  # gap in the sequence
            [(1, ConfigChange.INSTALLED), (2, ConfigChange.INSTALLED)],  # installed twice
            [(1, ConfigChange.REMOVED)],  # removed while loose
        ],
    )
    def test_broken_history_is_detected(self, history: list[tuple[int, ConfigChange]]) -> None:
        with pytest.raises(RuleViolation, match="history"):
            current_placement([event(n, change) for n, change in history])

    def test_removal_from_another_airframe_is_detected(self) -> None:
        other = AssetId(uuid7())
        with pytest.raises(RuleViolation, match="removes wrongly"):
            current_placement(
                [event(1, ConfigChange.INSTALLED), event(2, ConfigChange.REMOVED, other)]
            )

    def test_cannot_install_on_itself(self) -> None:
        with pytest.raises(ValidationError, match="itself"):
            event(1, ConfigChange.INSTALLED, parent=MOTOR)

    def install(self, **overrides: Any) -> None:
        values: dict[str, Any] = {
            "component_type": T["MOTOR"], "component_status": AssetStatus(),
            "component_placement": None, "parent_type": T["DRONE_AIRFRAME"],
            "parent_status": AssetStatus(), "position": "Motor 2",
            "occupied_positions": ["Motor 1"],
        }  # fmt: skip
        check_install(**{**values, **overrides})

    def test_valid_install(self) -> None:
        self.install()

    def test_every_install_problem_is_reported(self) -> None:
        with pytest.raises(RuleViolation) as caught:
            self.install(
                component_type=T["TRIPOD"],
                component_status=AssetStatus(serviceability=Serviceability.UNSERVICEABLE),
                component_placement=Placement(DRONE, "Motor 3"),
                parent_type=T["GNSS_RECEIVER"],
                parent_status=AssetStatus(serviceability=Serviceability.RETIRED),
                position=" motor 1 ",
            )
        message = str(caught.value)
        for fragment in ("not a component", "drone airframe", "already installed", "grounded",
                         "retired airframe", "Motor 1 on this airframe"):  # fmt: skip
            assert fragment in message


def document(kind: DocumentKind, **values: Any) -> AssetDocument:
    return AssetDocument(
        id=DocumentId(uuid7()), asset_id=DRONE, kind=kind, reference="REF-1", **values
    )


class TestDocuments:
    def test_dates_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="valid-until date"):
            document(DocumentKind.INSURANCE)
        with pytest.raises(ValidationError, match="before the issue date"):
            document(DocumentKind.OTHER, issued_on=date(2026, 5, 1), valid_until=date(2026, 4, 1))

    def test_status_on_a_day(self) -> None:
        today = date(2026, 11, 8)
        assert document(DocumentKind.UIN).status_on(today) == "permanent"
        insurance = document(DocumentKind.INSURANCE, valid_until=date(2026, 12, 1))
        assert insurance.status_on(today) == "expiring"
        assert insurance.status_on(date(2026, 10, 1)) == "valid"
        assert insurance.status_on(date(2026, 12, 2)) == "expired"

    def test_kinds_allowed_per_type(self) -> None:
        assert DocumentKind.UIN in allowed_kinds(T["DRONE_AIRFRAME"])
        assert DocumentKind.CALIBRATION not in allowed_kinds(T["DRONE_AIRFRAME"])
        receiver = allowed_kinds(T["GNSS_RECEIVER"])
        assert DocumentKind.CALIBRATION in receiver and DocumentKind.UIN not in receiver
        assert allowed_kinds(T["TRIPOD"]) == [DocumentKind.OTHER]
        for item_type in DEFAULT_CATALOGUE:  # the helper agrees with the rule it mirrors
            for kind in DocumentKind:
                doc = document(kind, valid_until=date(2027, 1, 1))
                if kind in allowed_kinds(item_type):
                    check_document_for_type(doc, item_type)
                else:
                    with pytest.raises(RuleViolation):
                        check_document_for_type(doc, item_type)

    def test_compliance_problems(self) -> None:
        today = date(2026, 11, 8)
        problems = compliance_problems(T["DRONE_AIRFRAME"], [], today)
        assert [kind for kind, _ in problems] == ["danger", "danger"]
        ok = [
            document(DocumentKind.UIN),
            document(DocumentKind.INSURANCE, valid_until=date(2027, 6, 1)),
        ]
        assert compliance_problems(T["DRONE_AIRFRAME"], ok, today) == []
        assert compliance_problems(T["TRIPOD"], [], today) == []


def firmware(sequence: int, version: str, day: date) -> FirmwareRecord:
    return FirmwareRecord(
        id=EntryId(uuid7()), asset_id=DRONE, sequence=sequence, version=version, installed_on=day,
        recorded_at=NOW, recorded_by=UserId(uuid7()), command_id=CommandId(uuid7()),
    )  # fmt: skip


class TestFirmware:
    def test_versions_are_cleaned_and_checked(self) -> None:
        assert firmware(1, "  v04.02.01 ", date(2026, 1, 1)).version == "v04.02.01"
        with pytest.raises(ValidationError, match="firmware version"):
            firmware(1, "v1/2", date(2026, 1, 1))

    def test_new_records_must_follow_on(self) -> None:
        first = firmware(1, "v1", date(2026, 3, 1))
        assert current_version([]) is None and current_version([first]) == "v1"
        check_new_firmware([], first)
        check_new_firmware([first], firmware(2, "v2", date(2026, 4, 1)))
        with pytest.raises(RuleViolation) as caught:
            check_new_firmware([first], firmware(3, "v1", date(2026, 2, 1)))
        message = str(caught.value)
        assert (
            "meanwhile" in message and "backwards" in message and "already the current" in message
        )


class TestKits:
    def test_templates_need_distinct_lines(self) -> None:
        motor = T["MOTOR"].id
        with pytest.raises(ValidationError, match="at least one line"):
            KitTemplate(id=KitTemplateId(uuid7()), name="Empty", discipline="drone", lines=())
        with pytest.raises(ValidationError, match="only once"):
            KitTemplate(id=KitTemplateId(uuid7()), name="Twice", discipline="drone",
                        lines=(TemplateLine(item_type_id=motor, quantity=1),) * 2)  # fmt: skip

    def test_codes_are_normalised(self) -> None:
        assert Kit(id=KitId(uuid7()), code=" drone-01 ", name="Kit").code == "KIT-DRONE-01"
        with pytest.raises(ValidationError, match="kit code"):
            Kit(id=KitId(uuid7()), code="drone 01!", name="Kit")
        with pytest.raises(ValidationError, match="only once"):
            Kit(id=KitId(uuid7()), code="A1", name="Kit", members=(DRONE, DRONE))

    def test_completeness(self) -> None:
        template = next(t for t in DEFAULT_TEMPLATES if t.name == "DGPS set")
        assert not completeness(template, {}).complete
        members = {AssetId(uuid7()): line.item_type_id for line in template.lines
                   for _ in range(line.quantity)}  # fmt: skip
        assert completeness(template, members).complete
        extra = AssetId(uuid7())
        result = completeness(template, {**members, extra: T["LAPTOP"].id})
        assert result.complete and result.extra == {T["LAPTOP"].id: 1}

    def test_members(self) -> None:
        check_member(T["TRIPOD"], None)
        with pytest.raises(RuleViolation) as caught:
            check_member(T["GCP_BANNER"], "KIT-DGPS-01")
        assert "counted stock" in str(caught.value) and "KIT-DGPS-01" in str(caught.value)
