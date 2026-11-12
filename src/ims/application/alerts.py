"""The alert centre: everything that needs someone's attention, in one list.

Combines maintenance (overdue and due tasks), defects, batteries (limits, health, storage
charge), calibration, compliance documents, pilot certificates, GCP stock and reservations
waiting for approval. Alerts are calculated each time, never stored; a fixed problem simply
stops appearing.
"""

from __future__ import annotations

from dataclasses import dataclass

from ims.application.airworthiness import battery_state_of, task_states
from ims.application.context import Actor
from ims.domain.assets.calibration import failed_reason
from ims.domain.assets.catalogue import Category, TrackingMode
from ims.domain.assets.documents import AssetDocument, compliance_problems
from ims.domain.assets.status import Serviceability, replay
from ims.domain.batteries import BatteryCondition
from ims.domain.common.ids import AssetId
from ims.domain.identity.roles import Permission, Role
from ims.domain.maintenance.defects import DefectState
from ims.domain.maintenance.programme import DueState
from ims.domain.operations.reservation import ReservationStatus
from ims.domain.stock.ledger import needs_reorder, position
from ims.ports.clock import Clock
from ims.ports.repository import Storage

SEVERITY_ORDER = {"danger": 0, "warning": 1, "info": 2}


@dataclass(frozen=True, slots=True)
class Alert:
    severity: str  # danger | warning | info
    # maintenance | defect | battery | calibration | document | licence | stock | reservation
    category: str
    title: str  # e.g. "DRN-0002 · Drone airframe"
    message: str
    section: str  # the page that deals with it
    asset_id: str = ""


class AlertService:
    def __init__(self, storage: Storage, clock: Clock) -> None:
        self._s = storage
        self._clock = clock

    def alerts(self, actor: Actor) -> list[Alert]:
        """Everything this person should know about, most urgent first."""
        actor.require(Permission.ASSET_VIEW)
        today = self._clock.today()
        types = {t.id: t for t in self._s.item_types.list(include_inactive=True)}
        documents: dict[AssetId, list[AssetDocument]] = {}
        for document in self._s.documents.list():
            documents.setdefault(document.asset_id, []).append(document)
        alerts: list[Alert] = []
        add = alerts.append

        for asset in self._s.assets.list():
            item_type = types.get(asset.item_type_id)
            if item_type is None or not item_type.is_individually_tracked:
                continue
            status = replay(self._s.status_events.for_asset(asset.id))
            if status.serviceability is Serviceability.RETIRED:
                continue
            title = f"{asset.asset_tag} · {item_type.name}"
            aid = str(asset.id)
            for due in task_states(self._s, asset.id, today):
                if due.state is DueState.OVERDUE:
                    word = "life limit reached" if due.task.life_limit else "overdue"
                    add(
                        Alert(
                            "danger",
                            "maintenance",
                            title,
                            f"{due.task.name} {word} ({due.summary})",
                            "maintenance",
                            aid,
                        )
                    )
                elif due.state is DueState.DUE:
                    add(
                        Alert(
                            "warning",
                            "maintenance",
                            title,
                            f"{due.task.name} due, inside its tolerance ({due.summary})",
                            "maintenance",
                            aid,
                        )
                    )
                elif due.state is DueState.DUE_SOON:
                    add(
                        Alert(
                            "info",
                            "maintenance",
                            title,
                            f"{due.task.name} due soon ({due.summary})",
                            "maintenance",
                            aid,
                        )
                    )
            if item_type.category is Category.BATTERY:
                battery = battery_state_of(self._s, asset.id, today)
                if battery is not None:
                    for reason in battery.reasons:
                        add(
                            Alert(
                                "danger",
                                "battery",
                                title,
                                reason[0].upper() + reason[1:],
                                "batteries",
                                aid,
                            )
                        )
                    for warning in battery.warnings:
                        severity = (
                            "warning"
                            if battery.condition is BatteryCondition.STORAGE_DUE
                            or "cycles left" in warning
                            else "info"
                        )
                        add(
                            Alert(
                                severity,
                                "battery",
                                title,
                                warning[0].upper() + warning[1:],
                                "batteries",
                                aid,
                            )
                        )
            calibration = failed_reason(self._s.calibrations.for_asset(asset.id))
            if calibration is not None:
                add(
                    Alert(
                        "danger",
                        "calibration",
                        title,
                        calibration[0].upper() + calibration[1:],
                        "equipment",
                        aid,
                    )
                )
            for severity, message in compliance_problems(
                item_type, documents.get(asset.id, []), today
            ):
                add(Alert(severity, "document", title, message, "equipment", aid))

        manager = actor.has(Permission.MAINTENANCE_MANAGE)
        for defect in self._s.defects.list():
            owner = self._s.assets.get(defect.asset_id)
            title = f"{owner.asset_tag if owner else '?'} · {defect.number}"
            if defect.state is DefectState.GROUNDED:
                add(
                    Alert(
                        "danger",
                        "defect",
                        title,
                        f"Grounding defect: {defect.description}",
                        "maintenance",
                        str(defect.asset_id),
                    )
                )
            elif defect.state is DefectState.REPORTED and manager:
                add(
                    Alert(
                        "warning",
                        "defect",
                        title,
                        f"Waiting for assessment: {defect.description}",
                        "maintenance",
                        str(defect.asset_id),
                    )
                )
            elif defect.overdue_on(today):
                add(
                    Alert(
                        "danger",
                        "defect",
                        title,
                        f"Deferral ran out on {defect.deferred_until:%d %b}: {defect.description}",
                        "maintenance",
                        str(defect.asset_id),
                    )
                )

        for user in self._s.users.list():
            if not user.is_active or user.licence is None:
                continue
            if user.id != actor.user_id and not actor.has(Permission.USER_MANAGE):
                continue
            state = user.licence.status_on(today)
            whose = "Your" if user.id == actor.user_id else f"{user.full_name}'s"
            if state == "expired":
                add(
                    Alert(
                        "danger" if user.role is Role.PILOT else "warning",
                        "licence",
                        user.full_name,
                        f"{whose} DGCA pilot certificate expired on "
                        f"{user.licence.expires_on:%d %b %Y}",
                        "people",
                    )
                )
            elif state == "expiring":
                add(
                    Alert(
                        "warning",
                        "licence",
                        user.full_name,
                        f"{whose} DGCA pilot certificate expires on "
                        f"{user.licence.expires_on:%d %b %Y}",
                        "people",
                    )
                )

        if actor.has(Permission.STOCK_VIEW):
            sites = {s.id: s for s in self._s.sites.list(include_deleted=True)}
            for item_type in types.values():
                if item_type.tracking is not TrackingMode.CONSUMABLE:
                    continue
                stock = position(self._s.stock.for_item_type(item_type.id))
                for level in self._s.reorder_levels.list():
                    if level.item_type_id != item_type.id:
                        continue
                    on_hand = stock.on_hand_at(level.location_id)
                    if needs_reorder(on_hand, level.level):
                        site = sites.get(level.location_id)
                        add(
                            Alert(
                                "warning",
                                "stock",
                                f"{item_type.name}s · {site.code if site else '?'}",
                                f"{on_hand} on hand, at or below the reorder level "
                                f"of {level.level}",
                                "stock",
                            )
                        )

        if actor.has(Permission.RESERVATION_APPROVE):
            waiting = [
                r for r in self._s.reservations.list() if r.status is ReservationStatus.REQUESTED
            ]
            if waiting:
                add(
                    Alert(
                        "info",
                        "reservation",
                        "Reservations",
                        f"{len(waiting)} request(s) waiting for approval",
                        "reservations",
                    )
                )

        return sorted(alerts, key=lambda a: (SEVERITY_ORDER[a.severity], a.category, a.title))
