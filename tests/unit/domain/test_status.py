import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ims.domain.assets.status import (
    INITIAL_STATUS,
    AssetStatus,
    Custody,
    Serviceability,
    StatusChange,
    StatusEvent,
    apply_change,
    replay,
    required_permissions,
)
from ims.domain.common.errors import InvalidTransition, RuleViolation
from ims.domain.common.ids import AssetId, CommandId, EntryId, ProjectId, UserId, uuid7
from ims.domain.identity.roles import Permission
from tests.fakes import START

S, C = Serviceability, Custody
PROJECT = ProjectId(uuid7())


def status(s: Serviceability = S.SERVICEABLE, c: Custody = C.IN_STORE) -> AssetStatus:
    return AssetStatus(serviceability=s, custody=c)


def change(
    s: Serviceability | None = None, c: Custody | None = None, reason: str = "checked"
) -> StatusChange:
    return StatusChange(
        serviceability=s, custody=c, reason=reason, project_id=PROJECT if c is C.DEPLOYED else None
    )


class TestTransitions:
    def test_new_assets_are_serviceable_and_in_store(self) -> None:
        assert status() == INITIAL_STATUS
        assert INITIAL_STATUS.is_deployable

    def test_normal_project_cycle(self) -> None:
        reserved = apply_change(status(), change(c=C.RESERVED))
        deployed = apply_change(reserved, change(c=C.DEPLOYED))
        returned = apply_change(deployed, change(c=C.IN_STORE))
        assert (reserved.custody, deployed.custody, returned.custody) == (
            C.RESERVED, C.DEPLOYED, C.IN_STORE,
        )  # fmt: skip

    def test_defect_in_the_field_keeps_custody(self) -> None:
        grounded = apply_change(status(c=C.DEPLOYED), change(s=S.UNSERVICEABLE))
        assert grounded == status(S.UNSERVICEABLE, C.DEPLOYED)
        assert not grounded.is_deployable

    def test_grounded_equipment_cannot_be_deployed(self) -> None:
        with pytest.raises(InvalidTransition, match="cannot be deployed"):
            apply_change(status(S.UNSERVICEABLE), change(c=C.DEPLOYED))

    def test_limited_equipment_can_be_deployed(self) -> None:
        assert apply_change(status(S.LIMITED), change(c=C.DEPLOYED)).custody is C.DEPLOYED

    def test_cannot_retire_while_deployed(self) -> None:
        with pytest.raises(InvalidTransition, match="back in store"):
            apply_change(status(c=C.DEPLOYED), change(s=S.RETIRED))

    def test_retired_equipment_can_only_be_disposed(self) -> None:
        retired = apply_change(status(), change(s=S.RETIRED))
        with pytest.raises(InvalidTransition, match="only be disposed"):
            apply_change(retired, change(c=C.IN_MAINTENANCE))
        with pytest.raises(InvalidTransition):
            apply_change(retired, change(s=S.SERVICEABLE))
        disposed = apply_change(retired, change(c=C.DISPOSED))
        assert disposed == status(S.RETIRED, C.DISPOSED)

    def test_only_retired_equipment_can_be_disposed(self) -> None:
        with pytest.raises(InvalidTransition, match="Only retired"):
            apply_change(status(), change(c=C.DISPOSED))

    def test_retire_and_dispose_together(self) -> None:
        assert apply_change(status(), change(s=S.RETIRED, c=C.DISPOSED)).custody is C.DISPOSED

    def test_disallowed_custody_move(self) -> None:
        with pytest.raises(InvalidTransition, match="from reserved to in_maintenance"):
            apply_change(status(c=C.RESERVED), change(c=C.IN_MAINTENANCE))

    def test_no_op_change_is_rejected(self) -> None:
        with pytest.raises(InvalidTransition, match="already has this status"):
            apply_change(status(), change(s=S.SERVICEABLE))

    def test_grounding_needs_a_reason(self) -> None:
        with pytest.raises(InvalidTransition, match="reason is required"):
            apply_change(status(), change(s=S.UNSERVICEABLE, reason="  "))

    def test_change_must_change_something_and_deployment_needs_project(self) -> None:
        with pytest.raises(RuleViolation, match="must change"):
            StatusChange.build()
        with pytest.raises(RuleViolation, match="requires a project"):
            StatusChange.build(custody=C.DEPLOYED)


class TestPermissions:
    @pytest.mark.parametrize(
        ("current", "requested", "needed"),
        [
            (status(), change(s=S.UNSERVICEABLE), {Permission.DEFECT_REPORT}),
            (status(S.LIMITED), change(s=S.UNSERVICEABLE), {Permission.DEFECT_REPORT}),
            (status(S.UNSERVICEABLE), change(s=S.SERVICEABLE), {Permission.MAINTENANCE_CERTIFY}),
            (status(S.LIMITED), change(s=S.SERVICEABLE), {Permission.MAINTENANCE_CERTIFY}),
            (status(), change(s=S.RETIRED), {Permission.ASSET_RETIRE}),
            (status(), change(c=C.RESERVED), {Permission.RESERVATION_CREATE}),
            (status(c=C.RESERVED), change(c=C.IN_STORE), {Permission.RESERVATION_CREATE}),
            (status(), change(c=C.DEPLOYED), {Permission.DEPLOYMENT_CREATE}),
            (status(c=C.DEPLOYED), change(c=C.IN_STORE), {Permission.DEPLOYMENT_RETURN}),
            (status(c=C.DEPLOYED), change(c=C.IN_MAINTENANCE), {Permission.DEPLOYMENT_RETURN}),
            (status(), change(c=C.IN_MAINTENANCE), {Permission.MAINTENANCE_MANAGE}),
            (status(c=C.IN_TRANSIT), change(c=C.IN_STORE), {Permission.MAINTENANCE_MANAGE}),
        ],
    )
    def test_required_permissions(
        self, current: AssetStatus, requested: StatusChange, needed: set[Permission]
    ) -> None:
        assert required_permissions(current, requested) == needed


def _event(n: int, before: AssetStatus, after: AssetStatus, asset: AssetId) -> StatusEvent:
    return StatusEvent(
        id=EntryId(uuid7()), asset_id=asset, sequence=n, command_id=CommandId(uuid7()),
        recorded_at=START, recorded_by=UserId(uuid7()), before=before, after=after,
    )  # fmt: skip


class TestReplay:
    def test_replays_history_to_current_status(self) -> None:
        asset = AssetId(uuid7())
        deployed = status(c=C.DEPLOYED)
        events = [
            _event(1, INITIAL_STATUS, deployed, asset),
            _event(2, deployed, status(S.UNSERVICEABLE, C.DEPLOYED), asset),
        ]
        assert replay(events) == status(S.UNSERVICEABLE, C.DEPLOYED)
        assert replay([]) == INITIAL_STATUS

    def test_broken_history_is_detected(self) -> None:
        asset = AssetId(uuid7())
        with pytest.raises(InvalidTransition, match="history is broken"):
            replay([_event(1, status(c=C.DEPLOYED), status(), asset)])
        with pytest.raises(InvalidTransition, match="history is broken"):
            replay([_event(2, INITIAL_STATUS, status(c=C.RESERVED), asset)])


changes = (
    st.tuples(
        st.none() | st.sampled_from(Serviceability),
        st.none() | st.sampled_from(Custody),
        st.sampled_from(["", "inspection"]),
    )
    .filter(lambda t: t[0] is not None or t[1] is not None)
    .map(lambda t: change(t[0], t[1], t[2]))
)


@settings(max_examples=300)
@given(st.lists(st.builds(lambda: None) | changes, max_size=30))
def test_random_change_sequences_never_break_the_rules(requests: list[StatusChange | None]) -> None:
    """Whatever sequence of requests users make, accepted states always obey the rules."""
    current = INITIAL_STATUS
    for request in requests:
        if request is None:
            continue
        try:
            new = apply_change(current, request)
        except InvalidTransition:
            continue
        if new.custody is C.DEPLOYED and current.custody is not C.DEPLOYED:
            assert current.serviceability in {S.SERVICEABLE, S.LIMITED}
        if new.custody is C.DISPOSED:
            assert new.serviceability is S.RETIRED
        if new.serviceability is S.RETIRED:
            assert new.custody in {C.IN_STORE, C.IN_MAINTENANCE, C.DISPOSED}
        if current.custody is C.DISPOSED:
            pytest.fail("nothing may change after disposal")
        current = new
