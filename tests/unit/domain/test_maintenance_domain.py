"""Rules added in Sprint 7: the maintenance programme, due calculation, defects, work orders."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from ims.domain.assets.catalogue import DEFAULT_CATALOGUE, Meter
from ims.domain.common.errors import InvalidTransition, RuleViolation
from ims.domain.common.ids import (
    AssetId,
    CommandId,
    DefectId,
    EntryId,
    MaintenanceTaskId,
    UserId,
    WorkOrderId,
    uuid7,
)
from ims.domain.maintenance.defects import (
    Defect,
    DefectState,
    check_defect_transition,
    next_number,
)
from ims.domain.maintenance.programme import (
    DEFAULT_PROGRAMME,
    DueState,
    MaintenanceTask,
    TaskCompletion,
    check_new_completion,
    due_status,
    last_completions,
)
from ims.domain.maintenance.work_orders import (
    WorkOrder,
    WorkOrderState,
    check_work_order_transition,
)

DAY = date(2026, 11, 12)
NOW = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)
H = Meter.HOURS
TYPE = {t.code: t for t in DEFAULT_CATALOGUE}["DRONE_AIRFRAME"].id


def task(**values: Any) -> MaintenanceTask:
    data: dict[str, Any] = {
        "id": MaintenanceTaskId(uuid7()),
        "item_type_id": TYPE,
        "name": "Inspection",
        "effective_from": DAY,
    }
    data.update(values)
    return MaintenanceTask(**data)


def done(t: MaintenanceTask, seq: int, on: date, hours: str) -> TaskCompletion:
    return TaskCompletion(
        id=EntryId(uuid7()),
        asset_id=AssetId(uuid7()),
        sequence=seq,
        task_id=t.id,
        done_on=on,
        meters={H: Decimal(hours)},
        recorded_at=NOW,
        recorded_by=UserId(uuid7()),
        command_id=CommandId(uuid7()),
    )


class TestTask:
    def test_rules(self) -> None:
        with pytest.raises(ValidationError, match="at least one interval"):
            task()
        with pytest.raises(ValidationError, match="not days"):
            task(every_days=30, life_limit=True)
        with pytest.raises(ValidationError, match="no tolerance"):
            task(every_hours=Decimal(100), life_limit=True, tolerance_hours=Decimal(5))
        t = task(
            every_hours=Decimal(50),
            every_cycles=200,
            every_landings=300,
            tolerance_cycles=5,
            tolerance_landings=10,
        )
        assert t.limits() == {Meter.HOURS: 50, Meter.CYCLES: 200, Meter.LANDINGS: 300}
        assert t.tolerance(Meter.CYCLES) == 5 and t.tolerance(Meter.LANDINGS) == 10

    def test_default_programme_builds(self) -> None:
        tasks = [d.build(DAY) for d in DEFAULT_PROGRAMME]
        assert len({t.id for t in tasks}) == len(tasks)
        assert sum(t.life_limit for t in tasks) == 2


class TestDue:
    def test_hours_states(self) -> None:
        t = task(every_hours=Decimal(50), tolerance_hours=Decimal(5))

        def state(hours: str) -> DueState:
            return due_status(t, meters={H: Decimal(hours)}, today=DAY, last=None, start=DAY).state

        assert [state(h) for h in ("10", "46", "52", "57")] == [
            DueState.OK,
            DueState.DUE_SOON,
            DueState.DUE,
            DueState.OVERDUE,
        ]
        last = done(t, 1, DAY, "40")
        after = due_status(t, meters={H: Decimal(57)}, today=DAY, last=last, start=DAY)
        assert after.state is DueState.OK and after.summary == "33 h left"
        assert after.last_done == DAY

    def test_days_states_and_summaries(self) -> None:
        t = task(every_days=90, tolerance_days=7)

        def due(on: date) -> Any:
            return due_status(t, meters={}, today=on, last=None, start=DAY)

        assert due(DAY).state is DueState.OK and due(DAY).due_on == DAY + timedelta(days=90)
        assert due(DAY + timedelta(days=85)).state is DueState.DUE_SOON
        assert due(DAY + timedelta(days=90)).state is DueState.DUE
        assert due(DAY + timedelta(days=90)).summary == "due now"
        assert due(DAY + timedelta(days=95)).state is DueState.DUE
        late = due(DAY + timedelta(days=100))
        assert late.state is DueState.OVERDUE and late.summary == "10 days over"
        both = task(every_hours=Decimal(50), every_days=90)
        mixed = due_status(both, meters={H: Decimal(10)}, today=DAY, last=None, start=DAY)
        assert mixed.summary == "40 h or 90 days left"

    def test_life_limits_never_reset(self) -> None:
        life = task(every_hours=Decimal(600), life_limit=True)
        last = done(life, 1, DAY, "590")
        reached = due_status(life, meters={H: Decimal(600)}, today=DAY, last=last, start=DAY)
        assert reached.state is DueState.OVERDUE and reached.summary == "limit reached"
        past = due_status(life, meters={H: Decimal(612)}, today=DAY, last=None, start=DAY)
        assert past.summary == "limit reached (12 h over)"
        assert due_status(
            task(every_cycles=10), meters={}, today=DAY, last=None, start=DAY
        ).state is (DueState.OK)

    def test_completions(self) -> None:
        t = task(every_hours=Decimal(50))
        first, second = done(t, 1, DAY - timedelta(days=5), "10"), done(t, 2, DAY, "40")
        assert last_completions([first, second])[t.id] == second
        check_new_completion([first], second, DAY)
        with pytest.raises(RuleViolation) as caught:
            check_new_completion([second], done(t, 3, DAY + timedelta(days=1), "45"), DAY)
        assert "meanwhile" in str(caught.value) and "future" in str(caught.value)
        with pytest.raises(RuleViolation, match="later date"):
            check_new_completion([second], done(t, 2, DAY - timedelta(days=9), "45"), DAY)


def defect(**values: Any) -> Defect:
    data: dict[str, Any] = {
        "id": DefectId(uuid7()),
        "number": "DEF-0001",
        "asset_id": AssetId(uuid7()),
        "description": "Arm creaks",
        "reported_by": UserId(uuid7()),
        "reported_at": NOW,
        "found_on": DAY,
    }
    data.update(values)
    return Defect(**data)


class TestDefects:
    def test_rules_and_transitions(self) -> None:
        with pytest.raises(ValidationError) as caught:
            defect(state=DefectState.DEFERRED)
        assert "limitation" in str(caught.value) and "date" in str(caught.value)
        with pytest.raises(ValidationError, match="work order"):
            defect(state=DefectState.RECTIFIED)
        with pytest.raises(ValidationError, match="not a defect"):
            defect(state=DefectState.CANCELLED)
        deferred = defect(
            state=DefectState.DEFERRED, limitation="Max wind 8 m/s", deferred_until=DAY
        )
        assert deferred.is_open and not deferred.overdue_on(DAY)
        assert deferred.overdue_on(DAY + timedelta(days=1))
        check_defect_transition(deferred, DefectState.GROUNDED)
        with pytest.raises(InvalidTransition):
            check_defect_transition(deferred, DefectState.CANCELLED)
        fixed = defect(state=DefectState.RECTIFIED, work_order_id=WorkOrderId(uuid7()))
        assert not fixed.is_open

    def test_numbers(self) -> None:
        assert next_number("DEF", []) == "DEF-0001"
        assert next_number("WO", ["WO-0001", "WO-0009", "WO-X"]) == "WO-0010"


def order(**values: Any) -> WorkOrder:
    data: dict[str, Any] = {
        "id": WorkOrderId(uuid7()),
        "number": "WO-0001",
        "asset_id": AssetId(uuid7()),
        "title": "Inspection",
        "opened_by": UserId(uuid7()),
        "opened_at": NOW,
    }
    data.update(values)
    return WorkOrder(**data)


class TestWorkOrders:
    def test_rules(self) -> None:
        t = MaintenanceTaskId(uuid7())
        d = DefectId(uuid7())
        with pytest.raises(ValidationError) as caught:
            order(task_ids=(t, t), defect_ids=(d, d))
        assert "each task once" in str(caught.value) and "each defect once" in str(caught.value)
        with pytest.raises(ValidationError) as caught:
            order(state=WorkOrderState.CERTIFIED)
        message = str(caught.value)
        assert "work done" in message and "who did it" in message and "signed it off" in message
        with pytest.raises(ValidationError, match="why"):
            order(state=WorkOrderState.CANCELLED)
        assert order().is_open and not order(state=WorkOrderState.CANCELLED, note="x").is_open

    def test_transitions(self) -> None:
        o = order()
        check_work_order_transition(o, WorkOrderState.IN_PROGRESS)
        with pytest.raises(InvalidTransition, match="open cannot become completed"):
            check_work_order_transition(o, WorkOrderState.COMPLETED)
        waiting = order(state=WorkOrderState.AWAITING_PARTS)
        check_work_order_transition(waiting, WorkOrderState.IN_PROGRESS)
        with pytest.raises(InvalidTransition, match="awaiting parts cannot become certified"):
            check_work_order_transition(waiting, WorkOrderState.CERTIFIED)
