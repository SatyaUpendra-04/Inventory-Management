"""Rules added in Sprint 6: reservations, the booking ledger and the conflict check."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from ims.domain.assets.status import AssetStatus, Custody, Serviceability
from ims.domain.common.errors import InvalidTransition
from ims.domain.common.ids import (
    AssetId,
    CommandId,
    DeploymentId,
    EntryId,
    LocationId,
    ProjectId,
    ReservationId,
    UserId,
    uuid7,
)
from ims.domain.operations.reservation import (
    AssetSchedule,
    BookingChange,
    BookingEvent,
    GcpForecast,
    Reservation,
    ReservationStatus,
    active_bookings,
    booking_label,
    check_conflicts,
    check_reservation_transition,
    clashing,
    overlaps,
)

DAY = date(2026, 11, 12)
NOW = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)
D = timedelta(days=1)


def reservation(**values: Any) -> Reservation:
    data: dict[str, Any] = {
        "id": ReservationId(uuid7()), "project_id": ProjectId(uuid7()),
        "asset_ids": (AssetId(uuid7()),), "starts_on": DAY, "ends_on": DAY + 4 * D,
        "requested_by": UserId(uuid7()), "requested_at": NOW,
    }  # fmt: skip
    data.update(values)
    return Reservation(**data)


class TestReservation:
    def test_rules(self) -> None:
        a = AssetId(uuid7())
        with pytest.raises(ValidationError) as caught:
            reservation(ends_on=DAY - D, asset_ids=(a, a), gcp_quantity=5)
        message = str(caught.value)
        assert "end before it starts" in message and "only once" in message
        assert "store the GCP" in message
        with pytest.raises(ValidationError, match="at most 180"):
            reservation(ends_on=DAY + 200 * D)
        with pytest.raises(ValidationError, match="equipment or GCP"):
            reservation(asset_ids=())
        with pytest.raises(ValidationError, match="reason for rejecting"):
            reservation(status=ReservationStatus.REJECTED)
        with pytest.raises(ValidationError, match="names its deployment"):
            reservation(status=ReservationStatus.FULFILLED)
        done = reservation(status=ReservationStatus.FULFILLED, deployment_id=DeploymentId(uuid7()))
        assert not done.is_live and reservation().is_live
        assert reservation().covers(DAY + 2 * D) and not reservation().covers(DAY + 5 * D)

    def test_transitions(self) -> None:
        requested = reservation()
        check_reservation_transition(requested, ReservationStatus.APPROVED)
        approved = reservation(status=ReservationStatus.APPROVED)
        check_reservation_transition(approved, ReservationStatus.FULFILLED)
        with pytest.raises(InvalidTransition):
            check_reservation_transition(approved, ReservationStatus.REJECTED)
        with pytest.raises(InvalidTransition):
            check_reservation_transition(
                reservation(status=ReservationStatus.CANCELLED), ReservationStatus.APPROVED
            )

    def test_dates(self) -> None:
        assert overlaps(DAY, DAY + 2 * D, DAY + 2 * D, DAY + 5 * D)
        assert not overlaps(DAY, DAY + 1 * D, DAY + 2 * D, DAY + 5 * D)
        dash = chr(0x2013)
        assert booking_label("PRJ-1", DAY, DAY) == "PRJ-1, 12 Nov"
        assert booking_label("PRJ-1", DAY, DAY + 3 * D) == f"PRJ-1, 12 {dash} 15 Nov"
        assert booking_label("PRJ-1", DAY, DAY + 30 * D) == f"PRJ-1, 12 Nov {dash} 12 Dec"


class TestLedger:
    def event(self, seq: int, change: BookingChange, r: Reservation) -> BookingEvent:
        return BookingEvent(
            id=EntryId(uuid7()), asset_id=r.asset_ids[0], sequence=seq, change=change,
            reservation_id=r.id, project_id=r.project_id, starts_on=r.starts_on,
            ends_on=r.ends_on, recorded_at=NOW, recorded_by=UserId(uuid7()),
            command_id=CommandId(uuid7()),
        )  # fmt: skip

    def test_replay_and_clashes(self) -> None:
        first = reservation()
        later = reservation(starts_on=DAY + 10 * D, ends_on=DAY + 12 * D)
        events = [
            self.event(1, BookingChange.BOOKED, first),
            self.event(2, BookingChange.BOOKED, later),
            self.event(3, BookingChange.RELEASED, later),
        ]
        held = active_bookings(events)
        assert [b.reservation_id for b in held] == [first.id]
        assert clashing(held, DAY + 3 * D, DAY + 6 * D, ReservationId(uuid7()))
        assert clashing(held, DAY + 3 * D, DAY + 6 * D, first.id) == []

    @pytest.mark.parametrize(
        ("changes", "message"),
        [
            ([(2, BookingChange.BOOKED)], "broken"),
            ([(1, BookingChange.BOOKED), (2, BookingChange.BOOKED)], "books twice"),
            ([(1, BookingChange.RELEASED)], "releases wrongly"),
        ],
    )
    def test_broken_history(self, changes: list[tuple[int, BookingChange]], message: str) -> None:
        r = reservation()
        with pytest.raises(InvalidTransition, match=message):
            active_bookings([self.event(n, c, r) for n, c in changes])


def schedule(**values: Any) -> AssetSchedule:
    data: dict[str, Any] = {"asset_id": AssetId(uuid7()), "tag": "DRN-0001",
                            "type_name": "Drone airframe", "status": AssetStatus()}  # fmt: skip
    data.update(values)
    return AssetSchedule(**data)


class TestConflicts:
    def test_everything_that_can_get_in_the_way(self) -> None:
        s_, c_ = Serviceability, Custody
        result = check_conflicts(
            assets=[
                schedule(booked=["PRJ-X, 12 Nov"], requested=["PRJ-Y, 13 Nov"]),
                schedule(status=AssetStatus(serviceability=s_.RETIRED)),
                schedule(status=AssetStatus(serviceability=s_.UNSERVICEABLE)),
                schedule(status=AssetStatus(serviceability=s_.LIMITED, custody=c_.IN_MAINTENANCE)),
                schedule(
                    out_with="PRJ-Z (due back 20 Nov)",
                    documents=["UIN missing"],
                    maintenance=["50 h service"],
                ),
            ],
            starts_on=DAY, ends_on=DAY + 3 * D, today=DAY, gcp_quantity=30,
            gcp=GcpForecast(on_hand=40, already_booked=20, reorder_level=10),
            incomplete_kits=["KIT-DGPS-01"],
        )  # fmt: skip
        assert result.blockers == [
            "DRN-0001 (Drone airframe) is already booked for PRJ-X, 12 Nov.",
            "DRN-0001 (Drone airframe) is retired.",
        ]
        text = " | ".join(result.warnings)
        for fragment in ("also requested", "grounded", "limitation", "in maintenance",
                         "out with PRJ-Z", "UIN missing", "maintenance planned",
                         "KIT-DGPS-01 is incomplete", "10 short"):  # fmt: skip
            assert fragment in text, fragment

    def test_dates_and_gcp_levels(self) -> None:
        bad = check_conflicts(assets=[], starts_on=DAY, ends_on=DAY - D, today=DAY + D)
        assert bad.blockers == [
            "The booking cannot end before it starts.",
            "The booking cannot start in the past.",
            "Choose equipment or GCP banners to reserve.",
        ]
        level_20 = GcpForecast(on_hand=40, already_booked=0, reorder_level=20)
        low = check_conflicts(
            assets=[], starts_on=DAY, ends_on=DAY, today=DAY, gcp_quantity=25, gcp=level_20
        )
        assert low.ok and "would leave 15" in low.warnings[0]
        no_level = GcpForecast(on_hand=40, already_booked=0, reorder_level=None)
        fine = check_conflicts(
            assets=[], starts_on=DAY, ends_on=DAY, today=DAY, gcp_quantity=5, gcp=no_level
        )
        assert fine.ok and fine.warnings == []
        assert GcpForecast(10, 4, None).left_after(3) == 3
        assert LocationId(uuid7())  # ids are plain UUIDs
