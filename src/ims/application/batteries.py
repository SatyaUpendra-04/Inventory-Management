"""Battery lifecycle: limits per kind of battery, checks, charge cycles, and the list."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ims.application.airworthiness import battery_state_of, ground_if_needed
from ims.application.context import Actor, CommandContext
from ims.application.ledgers import append_usage
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import Category, ItemType, Meter
from ims.domain.assets.status import AssetStatus, replay
from ims.domain.batteries import (
    BatteryCheck,
    BatteryPolicy,
    BatteryState,
    ChargeState,
    check_new_battery_check,
    default_policies,
)
from ims.domain.common.errors import ConflictError, NotFound, RuleViolation
from ims.domain.common.ids import AssetId, BatteryPolicyId, EntryId
from ims.domain.identity.roles import Permission
from ims.domain.usage.ledger import UsageEntry, UsageSource
from ims.ports.clock import Clock
from ims.ports.repository import Storage


@dataclass(frozen=True, slots=True)
class BatteryRow:
    asset: Asset
    item_type: ItemType
    status: AssetStatus
    state: BatteryState
    chargers: list[Asset]  # chargers registered for this battery family


@dataclass(frozen=True, slots=True)
class BatteryDetail:
    row: BatteryRow
    checks: list[BatteryCheck]
    cycles: list[UsageEntry]  # the battery's cycle ledger, oldest first


class BatteryService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    # ------------------------------------------------------------------ queries

    def policies(self, actor: Actor) -> list[BatteryPolicy]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.battery_policies.list()

    def batteries(self, actor: Actor) -> list[BatteryRow]:
        """Every battery with its cycles, health and anything it needs."""
        actor.require(Permission.ASSET_VIEW)
        types = {t.id: t for t in self._s.item_types.list(include_inactive=True)}
        chargers: dict[str, list[Asset]] = {}
        batteries: list[tuple[Asset, ItemType]] = []
        for asset in self._s.assets.list():
            item_type = types.get(asset.item_type_id)
            if item_type is None or item_type.battery_family is None:
                continue
            if item_type.category is Category.BATTERY:
                batteries.append((asset, item_type))
            else:
                chargers.setdefault(item_type.battery_family, []).append(asset)
        return [self._row(a, t, chargers) for a, t in batteries]

    def battery(self, actor: Actor, asset_id: AssetId) -> BatteryDetail:
        actor.require(Permission.ASSET_VIEW)
        row = next((r for r in self.batteries(actor) if r.asset.id == asset_id), None)
        if row is None:
            raise NotFound("Battery not found.")
        cycles = [e for e in self._s.usage.for_asset(asset_id) if e.meter is Meter.CYCLES]
        return BatteryDetail(row, self._s.battery_checks.for_asset(asset_id), cycles)

    # ------------------------------------------------------------------ commands

    def install_default_policies(self, ctx: CommandContext) -> int:
        """Starting limits for each kind of battery (once); every value can be edited."""
        ctx.require_actor().require(Permission.MAINTENANCE_MANAGE)
        added: list[str] = []

        def execute() -> Outcome:
            for policy in default_policies():
                if (
                    self._s.item_types.get(policy.item_type_id) is not None
                    and self._s.battery_policies.get(policy.id) is None
                ):
                    add_once(self._s.battery_policies.add, policy)
                    added.append(str(policy.item_type_id))
            return Outcome("battery_policies", "defaults", None, {"added": added})

        self._run.run(ctx, "battery.install_defaults", execute)
        return len(added)

    def update_policy(
        self, ctx: CommandContext, policy_id: BatteryPolicyId, expected_version: int, *,
        cycle_limit: int, health_floor: int, idle_days: int, notes: str = "",
    ) -> None:  # fmt: skip
        ctx.require_actor().require(Permission.MAINTENANCE_MANAGE)

        def execute() -> Outcome:
            stored = self._s.battery_policies.get(policy_id)
            if stored is None:
                raise NotFound("Battery limits not found.")
            candidate = stored.next_version(cycle_limit=cycle_limit, health_floor=health_floor,
                                            idle_days=idle_days, notes=notes)  # fmt: skip
            if stored.version != expected_version:
                if stored.version == expected_version + 1 and stored.model_dump(
                    exclude={"version"}
                ) == candidate.model_dump(exclude={"version"}):
                    return Outcome("battery_policy", str(policy_id), None, None)
                raise ConflictError(
                    "These limits were changed by someone else. Reload and try again."
                )
            update_once(self._s.battery_policies.update,
                        lambda: self._s.battery_policies.get(policy_id), candidate)  # fmt: skip
            return Outcome("battery_policy", str(policy_id), stored.model_dump(mode="json"),
                           candidate.model_dump(mode="json"))  # fmt: skip

        self._run.run(ctx, "battery.update_limits", execute)

    def record_check(
        self, ctx: CommandContext, asset_id: AssetId, *, checked_on: date | None = None,
        health_pct: int | None = None, internal_resistance_mohm: Decimal | None = None,
        cell_imbalance_mv: int | None = None, swelling: bool = False, damage: bool = False,
        charge_state: ChargeState = ChargeState.UNKNOWN, notes: str = "",
    ) -> EntryId:  # fmt: skip
        """Records an inspection. Swelling, damage or low health grounds the battery."""
        actor = ctx.require_actor()
        actor.require(Permission.USAGE_RECORD)
        entry_id = EntryId(ctx.derive("battery-check"))

        def execute() -> Outcome:
            self._battery(asset_id)
            existing = self._s.battery_checks.for_asset(asset_id)
            done = next((c for c in existing if c.id == entry_id), None)
            if done is None:
                check = BatteryCheck.build(
                    id=entry_id, asset_id=asset_id, sequence=len(existing) + 1,
                    checked_on=checked_on or self._clock.today(), health_pct=health_pct,
                    internal_resistance_mohm=internal_resistance_mohm,
                    cell_imbalance_mv=cell_imbalance_mv, swelling=swelling, damage=damage,
                    charge_state=charge_state, notes=notes, recorded_at=self._clock.now(),
                    recorded_by=actor.user_id, command_id=ctx.command_id,
                )  # fmt: skip
                check_new_battery_check(existing, check, self._clock.today())
                add_once(self._s.battery_checks.append, check)
                done = check
            ground_if_needed(self._s, self._clock, ctx, actor, asset_id, "ground")
            return Outcome("battery_check", str(entry_id), None, done.model_dump(mode="json"))

        self._run.run(ctx, "battery.check", execute)
        return entry_id

    def log_charge_cycles(
        self, ctx: CommandContext, asset_id: AssetId, cycles: int, *,
        on: date | None = None, note: str = "",
    ) -> EntryId:  # fmt: skip
        """Charge cycles used outside flights and logged surveys (e.g. a receiver battery)."""
        actor = ctx.require_actor()
        actor.require(Permission.USAGE_RECORD)
        entry_id = EntryId(ctx.derive("usage"))
        if cycles <= 0:
            raise RuleViolation("Enter how many charge cycles.")

        def execute() -> Outcome:
            self._battery(asset_id)
            day = on or self._clock.today()
            if day > self._clock.today():
                raise RuleViolation("Charge cycles cannot be dated in the future.")
            entry = append_usage(
                self._s, self._clock, ctx, actor, asset_id, meter=Meter.CYCLES,
                amount=Decimal(cycles), occurred_on=day, source=UsageSource.CHARGE,
                note=note or "Charge cycles",
            )  # fmt: skip
            ground_if_needed(self._s, self._clock, ctx, actor, asset_id, "ground")
            return Outcome("usage_entry", str(entry_id), None, entry.model_dump(mode="json"))

        self._run.run(ctx, "battery.charge_cycles", execute)
        return entry_id

    # ------------------------------------------------------------------ helpers

    def _row(
        self, asset: Asset, item_type: ItemType, chargers: dict[str, list[Asset]]
    ) -> BatteryRow:
        state = battery_state_of(self._s, asset.id, self._clock.today())
        if state is None:  # pragma: no cover - only called for batteries
            raise NotFound("Battery not found.")
        return BatteryRow(
            asset=asset, item_type=item_type,
            status=replay(self._s.status_events.for_asset(asset.id)), state=state,
            chargers=sorted(chargers.get(item_type.battery_family or "", []),
                            key=lambda a: a.asset_tag),
        )  # fmt: skip

    def _battery(self, asset_id: AssetId) -> Asset:
        asset = self._s.assets.get(asset_id)
        if asset is None or asset.is_deleted:
            raise NotFound("Battery not found.")
        item_type = self._s.item_types.get(asset.item_type_id)
        if item_type is None or item_type.category is not Category.BATTERY:
            raise RuleViolation(f"{asset.asset_tag} is not a battery.")
        return asset
