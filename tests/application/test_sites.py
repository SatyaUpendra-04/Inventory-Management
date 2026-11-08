from decimal import Decimal

import pytest

from ims.domain.assets.catalogue import default_item_type_id
from ims.domain.common.errors import ConflictError, NotFound, PermissionDenied, RuleViolation
from ims.domain.common.ids import LocationId, uuid7
from ims.domain.sites.site import SiteKind, SiteStatus
from ims.domain.stock.ledger import MovementKind
from tests.application.conftest import App

STORE = {"code": "main-store", "name": "Main store", "kind": SiteKind.STORE, "region": "Odisha"}


def test_create_update_and_list(app: App) -> None:
    site_id = app.sites.create(app.ctx(app.admin), **STORE)
    site = app.sites.get(app.actor(app.pilot), site_id)
    assert site.code == "MAIN-STORE" and site.label == "MAIN-STORE · Main store"
    app.sites.update(
        app.ctx(app.admin), site_id, 1, latitude=Decimal("21.5"), longitude=Decimal("85.3")
    )
    assert app.sites.get(app.actor(app.admin), site_id).version == 2
    assert [s.code for s in app.sites.list_sites(app.actor(app.surveyor))] == ["MAIN-STORE"]


def test_rules_and_permissions(app: App) -> None:
    with pytest.raises(PermissionDenied):
        app.sites.create(app.ctx(app.pilot), **STORE)
    with pytest.raises(RuleViolation, match="both latitude and longitude"):
        app.sites.create(app.ctx(app.admin), **STORE, latitude=Decimal(10))
    with pytest.raises(RuleViolation, match="cannot be set here: owner"):
        app.sites.create(app.ctx(app.admin), **STORE, owner="x")
    app.sites.create(app.ctx(app.admin), **STORE)
    with pytest.raises(RuleViolation, match="already in use"):
        app.sites.create(app.ctx(app.admin), **{**STORE, "name": "Copy"})


def test_stale_update_and_retry(app: App) -> None:
    site_id = app.sites.create(app.ctx(app.admin), **STORE)
    ctx = app.ctx(app.admin)
    app.sites.update(ctx, site_id, 1, status=SiteStatus.INACTIVE)
    app.sites.update(ctx, site_id, 1, status=SiteStatus.INACTIVE)  # retry: harmless
    with pytest.raises(ConflictError):
        app.sites.update(app.ctx(app.admin), site_id, 1, notes="stale")


def test_cannot_delete_a_site_holding_stock(app: App) -> None:
    site_id = app.sites.create(app.ctx(app.admin), **STORE)
    banner = default_item_type_id("GCP_BANNER")
    app.stock.record(
        app.ctx(app.admin),
        item_type_id=banner,
        location_id=site_id,
        kind=MovementKind.RECEIVED,
        quantity=12,
    )
    with pytest.raises(RuleViolation, match=r"still holds stock \(12 x GCP banner\)"):
        app.sites.delete(app.ctx(app.admin), site_id, 1)
    app.stock.record(
        app.ctx(app.admin),
        item_type_id=banner,
        location_id=site_id,
        kind=MovementKind.WRITTEN_OFF,
        quantity=12,
        reason="Weather damage",
    )
    app.sites.delete(app.ctx(app.admin), site_id, 1)
    app.sites.delete(app.ctx(app.admin), site_id, 1)  # already gone: no error
    assert app.sites.list_sites(app.actor(app.admin)) == []
    assert len(app.sites.list_sites(app.actor(app.admin), include_deleted=True)) == 1
    with pytest.raises(NotFound):
        app.sites.get(app.actor(app.admin), site_id)


def test_missing_and_stale_delete(app: App) -> None:
    with pytest.raises(NotFound):
        app.sites.delete(app.ctx(app.admin), LocationId(uuid7()), 1)
    site_id = app.sites.create(app.ctx(app.admin), **STORE)
    app.sites.update(app.ctx(app.admin), site_id, 1, notes="changed")
    with pytest.raises(ConflictError):
        app.sites.delete(app.ctx(app.admin), site_id, 1)
