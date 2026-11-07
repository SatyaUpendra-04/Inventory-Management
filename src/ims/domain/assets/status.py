"""Asset status as two independent state machines (ARCHITECTURE.md §4.1).

* **Serviceability:** can it be used?
* **Custody:** where is it?

Status is never stored as a mutable field. Every change is an appended
:class:`StatusEvent`, and the current status is the replay of those events.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from types import MappingProxyType

from pydantic import Field, model_validator

from ims.domain.common.errors import InvalidTransition
from ims.domain.common.ids import AssetId, CommandId, EntryId, ProjectId, UserId
from ims.domain.common.model import UtcDateTime, ValueModel
from ims.domain.identity.roles import Permission


class Serviceability(StrEnum):
    SERVICEABLE = "serviceable"
    LIMITED = "limited"  # serviceable with a deferred defect / limitation
    UNSERVICEABLE = "unserviceable"  # grounded
    RETIRED = "retired"


class Custody(StrEnum):
    IN_STORE = "in_store"
    RESERVED = "reserved"
    DEPLOYED = "deployed"
    IN_MAINTENANCE = "in_maintenance"
    IN_TRANSIT = "in_transit"
    DISPOSED = "disposed"


_S, _C = Serviceability, Custody

SERVICEABILITY_TRANSITIONS: MappingProxyType[Serviceability, frozenset[Serviceability]] = (
    MappingProxyType(
        {
            _S.SERVICEABLE: frozenset({_S.LIMITED, _S.UNSERVICEABLE, _S.RETIRED}),
            _S.LIMITED: frozenset({_S.SERVICEABLE, _S.UNSERVICEABLE, _S.RETIRED}),
            _S.UNSERVICEABLE: frozenset({_S.SERVICEABLE, _S.LIMITED, _S.RETIRED}),
            _S.RETIRED: frozenset(),
        }
    )
)

CUSTODY_TRANSITIONS: MappingProxyType[Custody, frozenset[Custody]] = MappingProxyType(
    {
        _C.IN_STORE: frozenset(
            {_C.RESERVED, _C.DEPLOYED, _C.IN_MAINTENANCE, _C.IN_TRANSIT, _C.DISPOSED}
        ),
        _C.RESERVED: frozenset({_C.IN_STORE, _C.DEPLOYED}),
        _C.DEPLOYED: frozenset({_C.IN_STORE, _C.IN_MAINTENANCE}),
        _C.IN_MAINTENANCE: frozenset({_C.IN_STORE, _C.IN_TRANSIT, _C.DISPOSED}),
        _C.IN_TRANSIT: frozenset({_C.IN_STORE, _C.IN_MAINTENANCE}),
        _C.DISPOSED: frozenset(),
    }
)

USABLE: frozenset[Serviceability] = frozenset({_S.SERVICEABLE, _S.LIMITED})
REASON_REQUIRED: frozenset[Serviceability | Custody] = frozenset(
    {_S.LIMITED, _S.UNSERVICEABLE, _S.RETIRED, _C.DISPOSED}
)


class AssetStatus(ValueModel):
    serviceability: Serviceability = Serviceability.SERVICEABLE
    custody: Custody = Custody.IN_STORE

    @property
    def is_deployable(self) -> bool:
        return self.serviceability in USABLE and self.custody in {_C.IN_STORE, _C.RESERVED}


INITIAL_STATUS = AssetStatus()


class StatusChange(ValueModel):
    """A requested change to one or both dimensions."""

    serviceability: Serviceability | None = None
    custody: Custody | None = None
    reason: str = Field(default="", max_length=1000)
    project_id: ProjectId | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> StatusChange:
        if self.serviceability is None and self.custody is None:
            raise ValueError("a status change must change serviceability, custody or both")
        if self.custody is _C.DEPLOYED and self.project_id is None:
            raise ValueError("deploying an asset requires a project")
        return self


class StatusEvent(ValueModel):
    """Append-only record of one applied change."""

    id: EntryId
    asset_id: AssetId
    sequence: int = Field(ge=1)  # 1, 2, 3 ... per asset; storage rejects duplicates
    command_id: CommandId
    recorded_at: UtcDateTime
    recorded_by: UserId
    before: AssetStatus
    after: AssetStatus
    reason: str = ""
    project_id: ProjectId | None = None


def apply_change(current: AssetStatus, change: StatusChange) -> AssetStatus:
    """Returns the new status, or raises :class:`InvalidTransition` explaining why not."""
    new_s = change.serviceability or current.serviceability
    new_c = change.custody or current.custody

    s_moves = new_s is not current.serviceability
    c_moves = new_c is not current.custody
    if s_moves and new_s not in SERVICEABILITY_TRANSITIONS[current.serviceability]:
        raise InvalidTransition(
            f"Cannot change serviceability from {current.serviceability.value} to {new_s.value}."
        )
    if c_moves and new_c not in CUSTODY_TRANSITIONS[current.custody]:
        raise InvalidTransition(
            f"Cannot move an asset from {current.custody.value} to {new_c.value}."
        )
    if not s_moves and not c_moves:
        raise InvalidTransition("The asset already has this status.")

    # Rules that link the two dimensions.
    if new_c is _C.DEPLOYED and current.custody is not _C.DEPLOYED:
        if current.serviceability not in USABLE or new_s not in USABLE:
            raise InvalidTransition("Grounded or retired equipment cannot be deployed.")
        if s_moves:
            # Return to service is its own certified step; never combined with deployment.
            raise InvalidTransition("Change serviceability and deploy as separate steps.")
    if new_s is _S.RETIRED and new_c not in {_C.IN_STORE, _C.IN_MAINTENANCE, _C.DISPOSED}:
        raise InvalidTransition(
            "Equipment must be back in store or in maintenance before it is retired."
        )
    if current.serviceability is _S.RETIRED and new_c is not _C.DISPOSED:
        raise InvalidTransition("Retired equipment can only be disposed of.")
    if new_c is _C.DISPOSED and new_s is not _S.RETIRED:
        raise InvalidTransition("Only retired equipment can be disposed of.")

    needs_reason = (change.serviceability in REASON_REQUIRED) or (change.custody in REASON_REQUIRED)
    if needs_reason and not change.reason.strip():
        raise InvalidTransition("A reason is required for this change.")

    return AssetStatus(serviceability=new_s, custody=new_c)


def replay(events: Iterable[StatusEvent]) -> AssetStatus:
    """Current status from history; verifies the history is a valid chain."""
    status = INITIAL_STATUS
    for expected, event in enumerate(events, start=1):
        if event.sequence != expected or event.before != status:
            raise InvalidTransition(f"Status history is broken at event {event.id}.")
        status = event.after
    return status


def required_permissions(current: AssetStatus, change: StatusChange) -> frozenset[Permission]:
    """Permissions needed to make ``change`` from ``current``."""
    needed: set[Permission] = set()
    s, c = change.serviceability, change.custody
    if s in {_S.LIMITED, _S.UNSERVICEABLE} and current.serviceability is _S.SERVICEABLE:
        needed.add(Permission.DEFECT_REPORT)
    if s is _S.UNSERVICEABLE and current.serviceability is _S.LIMITED:
        needed.add(Permission.DEFECT_REPORT)
    if s in {_S.SERVICEABLE, _S.LIMITED} and current.serviceability is _S.UNSERVICEABLE:
        needed.add(Permission.MAINTENANCE_CERTIFY)
    if s is _S.SERVICEABLE and current.serviceability is _S.LIMITED:
        needed.add(Permission.MAINTENANCE_CERTIFY)
    if s is _S.RETIRED or c is _C.DISPOSED:
        needed.add(Permission.ASSET_RETIRE)
    if c is _C.RESERVED or (c is _C.IN_STORE and current.custody is _C.RESERVED):
        needed.add(Permission.RESERVATION_CREATE)
    if c is _C.DEPLOYED:
        needed.add(Permission.DEPLOYMENT_CREATE)
    if current.custody is _C.DEPLOYED and c in {_C.IN_STORE, _C.IN_MAINTENANCE}:
        needed.add(Permission.DEPLOYMENT_RETURN)
    if c in {_C.IN_MAINTENANCE, _C.IN_TRANSIT} and current.custody is not _C.DEPLOYED:
        needed.add(Permission.MAINTENANCE_MANAGE)
    if c is _C.IN_STORE and current.custody in {_C.IN_MAINTENANCE, _C.IN_TRANSIT}:
        needed.add(Permission.MAINTENANCE_MANAGE)
    return frozenset(needed)
