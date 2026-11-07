"""Roles and the permission matrix.

Permissions are checked in the application layer for user experience and enforced again
by the backend (SharePoint permissions or Row Level Security) in Sprint 10.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType


class Role(StrEnum):
    ADMIN = "admin"  # Manager/Admin: one role, several allowed
    PILOT = "pilot"
    SURVEYOR = "surveyor"


class Permission(StrEnum):
    # Reference data
    ASSET_VIEW = "asset.view"
    ASSET_MANAGE = "asset.manage"
    ASSET_RETIRE = "asset.retire"
    SITE_VIEW = "site.view"
    SITE_MANAGE = "site.manage"
    PROJECT_VIEW = "project.view"
    PROJECT_MANAGE = "project.manage"
    # People
    USER_MANAGE = "user.manage"
    USER_VIEW_CONTACT = "user.view_contact"
    # Field operations (append-only for crew)
    RESERVATION_CREATE = "reservation.create"
    RESERVATION_APPROVE = "reservation.approve"
    DEPLOYMENT_CREATE = "deployment.create"
    DEPLOYMENT_RETURN = "deployment.return"
    USAGE_RECORD = "usage.record"
    USAGE_CORRECT = "usage.correct"
    DEFECT_REPORT = "defect.report"
    # Stock
    STOCK_VIEW = "stock.view"
    STOCK_MOVE = "stock.move"  # issue to / return from / consume on a project
    STOCK_MANAGE = "stock.manage"  # receive, write off, adjust after a count
    # Maintenance
    MAINTENANCE_MANAGE = "maintenance.manage"
    MAINTENANCE_CERTIFY = "maintenance.certify"  # return to service
    # Oversight
    REPORT_VIEW = "report.view"
    AUDIT_VIEW = "audit.view"
    BACKUP_MANAGE = "backup.manage"


_CREW: frozenset[Permission] = frozenset(
    {
        Permission.ASSET_VIEW,
        Permission.SITE_VIEW,
        Permission.PROJECT_VIEW,
        Permission.RESERVATION_CREATE,
        Permission.DEPLOYMENT_CREATE,
        Permission.DEPLOYMENT_RETURN,
        Permission.USAGE_RECORD,
        Permission.DEFECT_REPORT,
        Permission.STOCK_VIEW,
        Permission.STOCK_MOVE,
    }
)

ROLE_PERMISSIONS: MappingProxyType[Role, frozenset[Permission]] = MappingProxyType(
    {
        Role.ADMIN: frozenset(Permission),
        Role.PILOT: _CREW,
        Role.SURVEYOR: _CREW,
    }
)
"""Which permissions each role has. Equipment-type limits (Pilots take drone equipment,
Surveyors take survey equipment) are deployment rules, not permissions."""


def permissions_for(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]
