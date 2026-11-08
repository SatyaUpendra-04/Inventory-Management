from __future__ import annotations

from dataclasses import dataclass

import pytest

from ims.adapters.files import MemoryFileStore
from ims.adapters.local_auth import LocalAuthProvider, MemoryCredentialStore, fast_hasher
from ims.adapters.memory import memory_storage
from ims.application.accounts import AccountService
from ims.application.assets import AssetService
from ims.application.catalogue import CatalogueService
from ims.application.context import Actor, CommandContext
from ims.application.deployments import DeploymentService
from ims.application.field_logs import FieldLogService
from ims.application.kits import KitService
from ims.application.projects import ProjectService
from ims.application.registry import RegistryService
from ims.application.runner import CommandRunner
from ims.application.sites import SiteService
from ims.application.stock import StockService
from ims.application.usage import UsageService
from ims.application.users import UserService
from ims.domain.common.ids import new_command_id
from ims.domain.identity.roles import Role
from ims.domain.identity.user import User
from ims.ports.repository import Storage
from tests.fakes import FixedClock, make_user


@dataclass
class App:
    storage: Storage
    clock: FixedClock
    users: UserService
    catalogue: CatalogueService
    assets: AssetService
    usage: UsageService
    stock: StockService
    sites: SiteService
    registry: RegistryService
    kits: KitService
    projects: ProjectService
    deployments: DeploymentService
    logs: FieldLogService
    accounts: AccountService
    auth: LocalAuthProvider
    files: MemoryFileStore
    admin: User
    pilot: User
    surveyor: User

    def actor(self, user: User) -> Actor:
        return Actor.from_user(user)

    def ctx(self, user: User | None) -> CommandContext:
        return CommandContext(new_command_id(), None if user is None else Actor.from_user(user))


@pytest.fixture
def app() -> App:
    storage = memory_storage()
    clock = FixedClock()
    runner = CommandRunner(storage, clock)
    admin, pilot, surveyor = make_user(Role.ADMIN), make_user(Role.PILOT), make_user(Role.SURVEYOR)
    for user in (admin, pilot, surveyor):
        storage.users.add(user)
    users = UserService(storage, runner, clock)
    auth = LocalAuthProvider(MemoryCredentialStore(), fast_hasher())
    files = MemoryFileStore()
    application = App(
        storage=storage,
        clock=clock,
        users=users,
        catalogue=CatalogueService(storage, runner),
        assets=AssetService(storage, runner, clock),
        usage=UsageService(storage, runner, clock),
        stock=StockService(storage, runner, clock),
        sites=SiteService(storage, runner, clock),
        registry=RegistryService(storage, runner, clock, files),
        kits=KitService(storage, runner, clock),
        projects=ProjectService(storage, runner, clock),
        deployments=DeploymentService(storage, runner, clock),
        logs=FieldLogService(storage, runner, clock),
        accounts=AccountService(storage, auth, files, users, runner, clock),
        auth=auth,
        files=files,
        admin=admin,
        pilot=pilot,
        surveyor=surveyor,
    )
    application.catalogue.install_defaults(application.ctx(admin))
    return application
