"""GNSS calibration and verification records.

A passing (or adjusted) calibration also files the certificate as the item's calibration
document in the same command, so expiry is checked in one place (Sprint 4 compliance).
A failed calibration or verification grounds the receiver until a later record passes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ims.application.airworthiness import ground_if_needed
from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner, Outcome, add_once
from ims.domain.assets.calibration import (
    CalibrationKind,
    CalibrationRecord,
    CalibrationResult,
    check_new_record,
)
from ims.domain.assets.documents import AssetDocument, DocumentKind, check_document_for_type
from ims.domain.common.errors import NotFound, RuleViolation
from ims.domain.common.ids import AssetId, DocumentId, EntryId
from ims.domain.files import DOCUMENT_KINDS, MAX_DOCUMENT_BYTES, check_upload
from ims.domain.identity.roles import Permission
from ims.ports.clock import Clock
from ims.ports.files import FileStore
from ims.ports.repository import Storage


class CalibrationService:
    def __init__(
        self, storage: Storage, runner: CommandRunner, clock: Clock, files: FileStore
    ) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock
        self._files = files

    def records(self, actor: Actor, asset_id: AssetId) -> list[CalibrationRecord]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.calibrations.for_asset(asset_id)

    def record(
        self,
        ctx: CommandContext,
        asset_id: AssetId,
        *,
        kind: CalibrationKind,
        done_on: date,
        method: str,
        reference: str,
        result: CalibrationResult,
        horizontal_mm: Decimal | None = None,
        vertical_mm: Decimal | None = None,
        valid_until: date | None = None,
        notes: str = "",
        certificate: bytes | None = None,
    ) -> EntryId:
        """Calibrations are recorded by administrators; field verifications by the crew too."""
        actor = ctx.require_actor()
        actor.require(
            Permission.ASSET_MANAGE
            if kind is CalibrationKind.CALIBRATION
            else Permission.USAGE_RECORD
        )
        entry_id = EntryId(ctx.derive("calibration"))
        file_ref = (
            self._files.put(
                certificate, check_upload(certificate, DOCUMENT_KINDS, MAX_DOCUMENT_BYTES)
            )
            if certificate is not None
            else None
        )

        def execute() -> Outcome:
            asset = self._s.assets.get(asset_id)
            if asset is None or asset.is_deleted:
                raise NotFound("Asset not found.")
            item_type = self._s.item_types.get(asset.item_type_id)
            if item_type is None or not item_type.tracks_calibration:
                raise RuleViolation(f"{asset.asset_tag} does not track calibration.")
            existing = self._s.calibrations.for_asset(asset_id)
            done = next((r for r in existing if r.id == entry_id), None)
            if done is None:
                document_id: DocumentId | None = None
                if kind is CalibrationKind.CALIBRATION and result is not CalibrationResult.FAIL:
                    document_id = DocumentId(ctx.derive("calibration-certificate"))
                    document = AssetDocument.build(
                        id=document_id, asset_id=asset_id, kind=DocumentKind.CALIBRATION,
                        reference=reference[:80], issuer=reference[:100], issued_on=done_on,
                        valid_until=valid_until, file=file_ref,
                        notes=f"{method}; result {result.value}",
                    )  # fmt: skip
                    check_document_for_type(document, item_type)
                    add_once(self._s.documents.add, document)
                record = CalibrationRecord.build(
                    id=entry_id, asset_id=asset_id, sequence=len(existing) + 1, kind=kind,
                    done_on=done_on, method=method, reference=reference, result=result,
                    horizontal_mm=horizontal_mm, vertical_mm=vertical_mm,
                    valid_until=valid_until, document_id=document_id, notes=notes,
                    recorded_at=self._clock.now(), recorded_by=actor.user_id,
                    command_id=ctx.command_id,
                )  # fmt: skip
                check_new_record(existing, record, self._clock.today())
                add_once(self._s.calibrations.append, record)
                done = record
            ground_if_needed(self._s, self._clock, ctx, actor, asset_id, "ground")
            return Outcome("calibration", str(entry_id), None, done.model_dump(mode="json"))

        self._run.run(ctx, f"calibration.{kind.value}", execute)
        return entry_id
