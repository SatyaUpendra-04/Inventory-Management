"""Batteries: cycles, health and limits for every battery, checks and charge cycles."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ims.application.batteries import BatteryRow
from ims.domain.batteries import BatteryCondition, ChargeState
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, BatteryPolicyId
from ims.ui.app_services import Services
from ims.ui.models.dict_list import DictListModel
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.equipment import SERVICEABILITY
from ims.ui.viewmodels.forms import describe_error, local_time, optional_date, text
from ims.ui.viewmodels.session import SessionViewModel

CONDITION_LABELS = {
    BatteryCondition.OK: ("success", "OK"),
    BatteryCondition.STORAGE_DUE: ("warning", "Storage charge due"),
    BatteryCondition.NEAR_LIMIT: ("warning", "Near cycle limit"),
    BatteryCondition.RETIRE: ("danger", "Retire"),
    BatteryCondition.UNSAFE: ("danger", "Unsafe"),
}
FAMILY_LABELS = {
    "drone_flight": "Drone flight",
    "gnss_receiver": "DGPS receiver",
    "controller": "Controller",
}
CHARGE_LABELS = [
    {"value": ChargeState.UNKNOWN.value, "label": "Not checked"},
    {"value": ChargeState.STORAGE.value, "label": "Storage charge"},
    {"value": ChargeState.FULL.value, "label": "Full"},
    {"value": ChargeState.LOW.value, "label": "Low"},
]

_ROLES = (
    "assetId",
    "tag",
    "type",
    "family",
    "cycles",
    "cyclesText",
    "cycleShare",
    "health",
    "lastCheck",
    "idle",
    "conditionKind",
    "conditionLabel",
    "condition",
    "serviceKind",
    "serviceLabel",
    "retired",
    "search",
)


def _optional(raw: Any, label: str, *, whole: bool) -> Any:
    value = "" if raw is None else str(raw).strip()
    if not value:
        return None
    try:
        return int(value) if whole else Decimal(value)
    except (ValueError, InvalidOperation) as exc:
        raise RuleViolation(f"{label} must be a {'whole ' if whole else ''}number.") from exc


class BatteriesViewModel(QObject):
    changed = Signal()
    detailChanged = Signal()  # noqa: N815
    saved = Signal(str)

    def __init__(
        self,
        session: SessionViewModel,
        services: Services,
        tasks: TaskQueue,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._sv = services
        self._tasks = tasks
        self._model = DictListModel(_ROLES, self)
        self._all: list[dict[str, Any]] = []
        self._filter = "all"
        self._search = ""
        self._error = ""
        self._detail: dict[str, Any] = {}
        self._detail_id: AssetId | None = None
        self._policies: list[dict[str, Any]] = []
        session.signedIn.connect(self._on_signed_in)

    # ------------------------------------------------------------------ properties

    def _model_get(self) -> DictListModel:
        return self._model

    def _error_get(self) -> str:
        return self._error

    def _count_get(self) -> int:
        return self._model.rowCount()

    def _attention_get(self) -> int:
        return sum(1 for r in self._all if r["condition"] != "ok" and not r["retired"])

    def _filter_get(self) -> str:
        return self._filter

    def _detail_get(self) -> dict[str, Any]:
        return self._detail

    def _policies_get(self) -> list[dict[str, Any]]:
        return list(self._policies)

    def _can_manage_get(self) -> bool:
        return self._session.can("maintenance.manage")

    def _can_record_get(self) -> bool:
        return self._session.can("usage.record")

    def _charge_states_get(self) -> list[dict[str, str]]:
        return list(CHARGE_LABELS)

    model = Property(QObject, _model_get, constant=True)
    error = Property(str, _error_get, notify=changed)
    count = Property(int, _count_get, notify=changed)
    attentionCount = Property(int, _attention_get, notify=changed)  # noqa: N815
    filter = Property(str, _filter_get, notify=changed)
    detail = Property(dict, _detail_get, notify=detailChanged)
    policies = Property(list, _policies_get, notify=changed)
    canManage = Property(bool, _can_manage_get, notify=changed)  # noqa: N815
    canRecord = Property(bool, _can_record_get, notify=changed)  # noqa: N815
    chargeStates = Property(list, _charge_states_get, constant=True)  # noqa: N815

    # ------------------------------------------------------------------ plumbing

    def _fail(self, exc: BaseException) -> None:
        self._error = describe_error(exc)
        self.changed.emit()

    def _run(self, work: Callable[[], Any], message: str) -> None:
        self._error = ""
        self.changed.emit()

        def done(_: Any) -> None:
            self.saved.emit(message)
            self.refresh()
            if self._detail_id is not None:
                self.openBattery(str(self._detail_id))

        self._tasks.submit(work, done, self._fail)

    def _on_signed_in(self) -> None:
        if self._session.can("maintenance.manage"):
            self._tasks.submit(
                lambda: self._sv.batteries.install_default_policies(self._session.context()),
                lambda _: self.refresh(),
                self._fail,
            )
        else:
            self.refresh()

    def _apply_filter(self) -> None:
        needle = self._search.strip().lower()
        rows = [
            r
            for r in self._all
            if (self._filter == "all" or (r["condition"] != "ok" and not r["retired"]))
            and (not needle or needle in r["search"])
        ]
        self._model.reset(rows)
        self.changed.emit()

    # ------------------------------------------------------------------ list

    def _row(self, r: BatteryRow) -> dict[str, Any]:
        s = r.state
        kind, label = CONDITION_LABELS[s.condition]
        service_kind, service_label = SERVICEABILITY[r.status.serviceability]
        retired = r.status.serviceability.value == "retired"
        if retired:
            kind, label = "neutral", "Retired"
        return {
            "assetId": str(r.asset.id),
            "tag": r.asset.asset_tag,
            "type": r.item_type.name,
            "family": FAMILY_LABELS.get(r.item_type.battery_family or "", ""),
            "cycles": s.cycles,
            "cyclesText": f"{s.cycles} / {s.cycle_limit}" if s.cycle_limit else str(s.cycles),
            "cycleShare": min(1.0, s.cycles / s.cycle_limit) if s.cycle_limit else 0.0,
            "health": s.health_text,
            "lastCheck": f"{s.last_check.checked_on:%d %b %Y}" if s.last_check else "",
            "idle": f"{s.idle_days} days" if s.idle_days is not None else "",
            "conditionKind": kind,
            "conditionLabel": label,
            "condition": s.condition.value,
            "serviceKind": service_kind,
            "serviceLabel": service_label,
            "retired": retired,
            "search": " ".join(
                [r.asset.asset_tag, r.asset.serial_number or "", r.item_type.name]
            ).lower(),
        }

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("asset.view"):
            return
        actor = self._session.actor()

        def work() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            rows = [self._row(r) for r in self._sv.batteries.batteries(actor)]
            types = {
                t.id: t.name
                for t in self._sv.catalogue.list_item_types(actor, include_inactive=True)
            }
            policies = [
                {
                    "policyId": str(p.id),
                    "version": p.version,
                    "type": types.get(p.item_type_id, "?"),
                    "cycleLimit": str(p.cycle_limit),
                    "healthFloor": str(p.health_floor),
                    "idleDays": str(p.idle_days),
                    "notes": p.notes,
                }
                for p in self._sv.batteries.policies(actor)
            ]
            return sorted(rows, key=lambda r: r["tag"]), policies

        def done(result: tuple[list[dict[str, Any]], list[dict[str, Any]]]) -> None:
            self._all, self._policies = result
            self._apply_filter()

        self._tasks.submit(work, done, self._fail)

    @Slot(str)
    def setFilter(self, value: str) -> None:  # noqa: N802
        self._filter = value
        self._apply_filter()

    @Slot(str)
    def setSearch(self, value: str) -> None:  # noqa: N802
        self._search = value
        self._apply_filter()

    @Slot()
    def clearError(self) -> None:  # noqa: N802
        self._error = ""
        self.changed.emit()

    # ------------------------------------------------------------------ one battery

    @Slot(str)
    def openBattery(self, asset_id: str) -> None:  # noqa: N802
        self._detail_id = AssetId(uuid.UUID(asset_id))
        actor = self._session.actor()

        def work() -> dict[str, Any]:
            d = self._sv.batteries.battery(actor, AssetId(uuid.UUID(asset_id)))
            people = {u.id: u.full_name for u in self._sv.users.crew_directory(actor)}
            charge = {c["value"]: c["label"] for c in CHARGE_LABELS}
            s = d.row.state
            return {
                **self._row(d.row),
                "serial": d.row.asset.serial_number or "",
                "cycleLimit": s.cycle_limit or 0,
                "measured": s.health_measured,
                "reasons": [r[0].upper() + r[1:] for r in s.reasons],
                "warnings": [w[0].upper() + w[1:] for w in s.warnings],
                "isDroneBattery": d.row.item_type.battery_family == "drone_flight",
                "chargers": ", ".join(c.asset_tag for c in d.row.chargers),
                "checks": [
                    {
                        "when": f"{c.checked_on:%d %b %Y}",
                        "health": f"{c.health_pct}%" if c.health_pct is not None else "—",
                        "resistance": f"{c.internal_resistance_mohm} mΩ"
                        if c.internal_resistance_mohm is not None
                        else "",
                        "imbalance": f"{c.cell_imbalance_mv} mV"
                        if c.cell_imbalance_mv is not None
                        else "",
                        "charge": charge[c.charge_state.value],
                        "flag": "Swelling" if c.swelling else ("Damage" if c.damage else ""),
                        "notes": c.notes,
                        "by": people.get(c.recorded_by, ""),
                    }
                    for c in reversed(d.checks)
                ],
                "history": [
                    {
                        "when": f"{e.occurred_on:%d %b %Y}",
                        "amount": f"{e.amount:+.0f}",
                        "source": e.source.value.replace("_", " ").capitalize(),
                        "note": e.note,
                        "recorded": local_time(e.recorded_at),
                    }
                    for e in reversed(d.cycles)
                ],
            }

        def done(detail: dict[str, Any]) -> None:
            self._detail = detail
            self.detailChanged.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot()
    def closeBattery(self) -> None:  # noqa: N802
        self._detail_id = None
        self._detail = {}
        self.detailChanged.emit()

    # ------------------------------------------------------------------ commands

    @Slot(str, dict)
    def recordCheck(self, asset_id: str, values: dict[str, Any]) -> None:  # noqa: N802
        fields = values.copy()

        def work() -> None:
            self._sv.batteries.record_check(
                self._session.context(),
                AssetId(uuid.UUID(asset_id)),
                checked_on=optional_date(fields, "checkedOn"),
                health_pct=_optional(fields.get("health"), "Health", whole=True),
                internal_resistance_mohm=_optional(
                    fields.get("resistance"), "Resistance", whole=False
                ),
                cell_imbalance_mv=_optional(fields.get("imbalance"), "Cell imbalance", whole=True),
                swelling=bool(fields.get("swelling")),
                damage=bool(fields.get("damage")),
                charge_state=ChargeState(text(fields, "chargeState") or ChargeState.UNKNOWN.value),
                notes=text(fields, "notes"),
            )

        self._run(work, "Battery check recorded")

    @Slot(str, str, str, str)
    def logCharge(self, asset_id: str, cycles: str, on: str, note: str) -> None:  # noqa: N802
        def work() -> None:
            count = _optional(cycles, "Cycles", whole=True)
            if count is None:
                raise RuleViolation("Enter how many charge cycles.")
            self._sv.batteries.log_charge_cycles(
                self._session.context(),
                AssetId(uuid.UUID(asset_id)),
                count,
                on=optional_date({"d": on}, "d"),
                note=note,
            )

        self._run(work, "Charge cycles logged")

    @Slot(str, int, dict)
    def updatePolicy(self, policy_id: str, version: int, values: dict[str, Any]) -> None:  # noqa: N802
        fields = values.copy()

        def work() -> None:
            limit = _optional(fields.get("cycleLimit"), "Cycle limit", whole=True)
            floor = _optional(fields.get("healthFloor"), "Health limit", whole=True)
            idle = _optional(fields.get("idleDays"), "Idle days", whole=True)
            if limit is None or floor is None or idle is None:
                raise RuleViolation("Enter the cycle limit, health limit and idle days.")
            self._sv.batteries.update_policy(
                self._session.context(),
                BatteryPolicyId(uuid.UUID(policy_id)),
                version,
                cycle_limit=limit,
                health_floor=floor,
                idle_days=idle,
                notes=text(fields, "notes"),
            )

        self._run(work, "Battery limits saved")
