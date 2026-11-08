"""SQLite table definitions (SQLAlchemy Core).

The schema is *created and changed only by Alembic migrations* in ``migrations/``.
These definitions are used for queries, and a test checks they match the migrated
database exactly.

Conventions: IDs are UUID strings; timestamps are ISO 8601 UTC strings ending in ``Z``;
dates are ISO strings; decimals are strings, so no precision is lost.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData(
    naming_convention={
        "pk": "pk_%(table_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    }
)

ID = 36  # length of a UUID string

users = Table(
    "users",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("username", String(32), nullable=False, unique=True),
    Column("full_name", String(100), nullable=False),
    Column("role", String(16), nullable=False),
    Column("employee_id", String(20), nullable=False, unique=True),
    Column("email", String(254), nullable=False, unique=True),
    Column("phone", String(20), nullable=False),
    Column("licence_number", String(40)),
    Column("licence_expires_on", String(10)),
    Column("licence_document", String(80)),
    Column("profile_picture", String(260)),
    Column("is_active", Boolean, nullable=False),
    Column("must_change_password", Boolean, nullable=False),
    Column("deleted_at", String(32)),
)

sites = Table(
    "sites",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("code", String(20), nullable=False, unique=True),
    Column("name", String(100), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("region", String(100), nullable=False),
    Column("latitude", String(24)),
    Column("longitude", String(24)),
    Column("area_hectares", String(24)),
    Column("mineral", String(60), nullable=False),
    Column("status", String(16), nullable=False),
    Column("notes", Text, nullable=False),
    Column("deleted_at", String(32)),
)

local_credentials = Table(
    "local_credentials",
    metadata,
    Column("user_id", String(ID), ForeignKey("users.id"), primary_key=True),
    Column("password_hash", String(200), nullable=False),
    Column("failed_attempts", Integer, nullable=False),
    Column("locked_until", String(32)),
    Column("changed_at", String(32)),
)

item_types = Table(
    "item_types",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("code", String(40), nullable=False, unique=True),
    Column("name", String(80), nullable=False),
    Column("category", String(32), nullable=False),
    Column("discipline", String(16), nullable=False),
    Column("tracking", String(16), nullable=False),
    Column("meters", String(64), nullable=False),  # comma-separated, sorted
    Column("is_component", Boolean, nullable=False),
    Column("tag_prefix", String(4)),
    Column("tracks_warranty", Boolean, nullable=False),
    Column("tracks_calibration", Boolean, nullable=False),
    Column("battery_family", String(40)),
    Column("is_active", Boolean, nullable=False),
)

assets = Table(
    "assets",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("item_type_id", String(ID), ForeignKey("item_types.id"), nullable=False),
    Column("asset_tag", String(17), nullable=False, unique=True),
    Column("serial_number", String(64)),
    Column("make", String(60)),
    Column("model", String(60)),
    Column("acquired_on", String(10)),
    Column("warranty_until", String(10)),
    Column("home_site_id", String(ID)),
    Column("notes", Text, nullable=False),
    Column("deleted_at", String(32)),
    UniqueConstraint("item_type_id", "serial_number"),
)

status_events = Table(
    "status_events",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("asset_id", String(ID), ForeignKey("assets.id"), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("command_id", String(ID), nullable=False),
    Column("recorded_at", String(32), nullable=False),
    Column("recorded_by", String(ID), nullable=False),
    Column("before_serviceability", String(16), nullable=False),
    Column("before_custody", String(16), nullable=False),
    Column("after_serviceability", String(16), nullable=False),
    Column("after_custody", String(16), nullable=False),
    Column("reason", Text, nullable=False),
    Column("project_id", String(ID)),
    UniqueConstraint("asset_id", "sequence"),
)

usage_entries = Table(
    "usage_entries",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("asset_id", String(ID), ForeignKey("assets.id"), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("meter", String(16), nullable=False),
    Column("amount", String(32), nullable=False),
    Column("occurred_on", String(10), nullable=False),
    Column("source", String(24), nullable=False),
    Column("recorded_at", String(32), nullable=False),
    Column("recorded_by", String(ID), nullable=False),
    Column("command_id", String(ID), nullable=False),
    Column("project_id", String(ID)),
    Column("reverses", String(ID), unique=True),
    Column("note", Text, nullable=False),
    UniqueConstraint("asset_id", "sequence"),
)

stock_movements = Table(
    "stock_movements",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("item_type_id", String(ID), ForeignKey("item_types.id"), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("location_id", String(ID), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("recorded_at", String(32), nullable=False),
    Column("recorded_by", String(ID), nullable=False),
    Column("command_id", String(ID), nullable=False),
    Column("project_id", String(ID)),
    Column("reason", Text, nullable=False),
    UniqueConstraint("item_type_id", "sequence"),
)

configuration_events = Table(
    "configuration_events",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("component_id", String(ID), ForeignKey("assets.id"), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("change", String(16), nullable=False),
    Column("parent_id", String(ID), ForeignKey("assets.id"), nullable=False),
    Column("position", String(40), nullable=False),
    Column("recorded_at", String(32), nullable=False),
    Column("recorded_by", String(ID), nullable=False),
    Column("command_id", String(ID), nullable=False),
    Column("note", Text, nullable=False),
    UniqueConstraint("component_id", "sequence"),
    Index(None, "parent_id"),
)

asset_documents = Table(
    "asset_documents",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("asset_id", String(ID), ForeignKey("assets.id"), nullable=False),
    Column("kind", String(24), nullable=False),
    Column("reference", String(80), nullable=False),
    Column("issuer", String(100), nullable=False),
    Column("issued_on", String(10)),
    Column("valid_until", String(10)),
    Column("file", String(80)),
    Column("notes", Text, nullable=False),
    Column("deleted_at", String(32)),
    Index(None, "asset_id"),
)

firmware_records = Table(
    "firmware_records",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("asset_id", String(ID), ForeignKey("assets.id"), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("version", String(40), nullable=False),
    Column("installed_on", String(10), nullable=False),
    Column("recorded_at", String(32), nullable=False),
    Column("recorded_by", String(ID), nullable=False),
    Column("command_id", String(ID), nullable=False),
    Column("note", Text, nullable=False),
    UniqueConstraint("asset_id", "sequence"),
)

kit_templates = Table(
    "kit_templates",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("name", String(60), nullable=False),
    Column("name_key", String(60), nullable=False, unique=True),  # lower-case, for uniqueness
    Column("discipline", String(16), nullable=False),
    Column("lines", Text, nullable=False),  # JSON list of item types and quantities
    Column("notes", Text, nullable=False),
    Column("is_active", Boolean, nullable=False),
)

kits = Table(
    "kits",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("code", String(20), nullable=False, unique=True),
    Column("name", String(80), nullable=False),
    Column("template_id", String(ID)),
    Column("members", Text, nullable=False),  # JSON list of asset IDs
    Column("home_site_id", String(ID)),
    Column("notes", Text, nullable=False),
    Column("deleted_at", String(32)),
)

reorder_levels = Table(
    "reorder_levels",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("item_type_id", String(ID), ForeignKey("item_types.id"), nullable=False),
    Column("location_id", String(ID), nullable=False),
    Column("level", Integer, nullable=False),
    UniqueConstraint("item_type_id", "location_id"),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("command_id", String(ID), nullable=False),
    Column("at", String(32), nullable=False),
    Column("actor_id", String(ID)),
    Column("action", String(80), nullable=False),
    Column("entity", String(80), nullable=False),
    Column("entity_id", String(80), nullable=False),
    Column("before_json", Text),
    Column("after_json", Text),
    Index(None, "entity", "entity_id"),
    Index(None, "at"),
)

command_log = Table(
    "command_log",
    metadata,
    Column("command_id", String(ID), primary_key=True),
    Column("action", String(80), nullable=False),
    Column("actor_id", String(ID)),
    Column("completed_at", String(32), nullable=False),
    Column("result_id", String(80), nullable=False),
)
