"""The application services the UI talks to (never storage or adapters directly)."""

from __future__ import annotations

from dataclasses import dataclass

from ims.application.accounts import AccountService
from ims.application.assets import AssetService
from ims.application.catalogue import CatalogueService
from ims.application.deployments import DeploymentService
from ims.application.field_logs import FieldLogService
from ims.application.kits import KitService
from ims.application.projects import ProjectService
from ims.application.registry import RegistryService
from ims.application.reservations import ReservationService
from ims.application.sites import SiteService
from ims.application.stock import StockService
from ims.application.users import UserService
from ims.ports.clock import Clock


@dataclass(frozen=True, slots=True)
class Services:
    accounts: AccountService
    users: UserService
    sites: SiteService
    catalogue: CatalogueService
    assets: AssetService
    registry: RegistryService
    kits: KitService
    stock: StockService
    projects: ProjectService
    deployments: DeploymentService
    logs: FieldLogService
    reservations: ReservationService
    clock: Clock
