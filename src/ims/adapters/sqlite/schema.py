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

projects = Table(
    "projects",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("code", String(24), nullable=False, unique=True),
    Column("name", String(120), nullable=False),
    Column("site_id", String(ID), ForeignKey("sites.id"), nullable=False),
    Column("client", String(120), nullable=False),
    Column("starts_on", String(10), nullable=False),
    Column("ends_on", String(10)),
    Column("chief_pilot_id", String(ID)),
    Column("surveyor_id", String(ID)),
    Column("status", String(16), nullable=False),
    Column("notes", Text, nullable=False),
    Column("deleted_at", String(32)),
)

deployments = Table(
    "deployments",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("project_id", String(ID), ForeignKey("projects.id"), nullable=False, index=True),
    Column("asset_ids", Text, nullable=False),  # JSON lists, as they will be on SharePoint
    Column("kit_ids", Text, nullable=False),
    Column("crew_ids", Text, nullable=False),
    Column("gcp_quantity", Integer, nullable=False),
    Column("gcp_site_id", String(ID)),
    Column("deployed_on", String(10), nullable=False),
    Column("created_at", String(32), nullable=False),
    Column("created_by", String(ID), nullable=False),
    Column("state", String(16), nullable=False),
    Column("notes", Text, nullable=False),
    Column("failure", Text, nullable=False),
    Column("returned_on", String(10)),
    Column("returned_by", String(ID)),
    Column("returns", Text, nullable=False),  # JSON list of {asset_id, condition, note}
    Column("gcp_returned", Integer, nullable=False),
    Column("gcp_consumed", Integer, nullable=False),
    Column("return_site_id", String(ID)),
    Column("reservation_id", String(ID)),
)

sorties = Table(
    "sorties",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("project_id", String(ID), ForeignKey("projects.id"), nullable=False, index=True),
    Column("deployment_id", String(ID), ForeignKey("deployments.id"), nullable=False),
    Column("drone_id", String(ID), ForeignKey("assets.id"), nullable=False),
    Column("pilot_id", String(ID), nullable=False),
    Column("flown_on", String(10), nullable=False),
    Column("hours", String(16), nullable=False),
    Column("landings", Integer, nullable=False),
    Column("cycles", Integer, nullable=False),
    Column("battery_ids", Text, nullable=False),
    Column("ppk_base_id", String(ID)),
    Column("media_ids", Text, nullable=False),
    Column("notes", Text, nullable=False),
    Column("recorded_at", String(32), nullable=False),
    Column("recorded_by", String(ID), nullable=False),
    Column("usage_entries", Text, nullable=False),
    Column("voided_at", String(32)),
    Column("void_reason", Text, nullable=False),
)

survey_sessions = Table(
    "survey_sessions",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("project_id", String(ID), ForeignKey("projects.id"), nullable=False, index=True),
    Column("deployment_id", String(ID), ForeignKey("deployments.id"), nullable=False),
    Column("surveyor_id", String(ID), nullable=False),
    Column("surveyed_on", String(10), nullable=False),
    Column("mode", String(16), nullable=False),
    Column("base_id", String(ID)),
    Column("rover_ids", Text, nullable=False),
    Column("controller_id", String(ID)),
    Column("hours", String(16), nullable=False),
    Column("area_ha", String(16)),
    Column("points", Integer, nullable=False),
    Column("fix_rate", String(8)),
    Column("battery_ids", Text, nullable=False),
    Column("notes", Text, nullable=False),
    Column("recorded_at", String(32), nullable=False),
    Column("recorded_by", String(ID), nullable=False),
    Column("usage_entries", Text, nullable=False),
    Column("voided_at", String(32)),
    Column("void_reason", Text, nullable=False),
)

reservations = Table(
    "reservations",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("project_id", String(ID), ForeignKey("projects.id"), nullable=False, index=True),
    Column("asset_ids", Text, nullable=False),
    Column("kit_ids", Text, nullable=False),
    Column("starts_on", String(10), nullable=False),
    Column("ends_on", String(10), nullable=False),
    Column("gcp_quantity", Integer, nullable=False),
    Column("gcp_site_id", String(ID)),
    Column("notes", Text, nullable=False),
    Column("requested_by", String(ID), nullable=False),
    Column("requested_at", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("decided_by", String(ID)),
    Column("decided_at", String(32)),
    Column("decision_note", Text, nullable=False),
    Column("deployment_id", String(ID)),
)

booking_events = Table(
    "booking_events",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("asset_id", String(ID), ForeignKey("assets.id"), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("change", String(16), nullable=False),
    Column("reservation_id", String(ID), ForeignKey("reservations.id"), nullable=False),
    Column("project_id", String(ID), nullable=False),
    Column("starts_on", String(10), nullable=False),
    Column("ends_on", String(10), nullable=False),
    Column("recorded_at", String(32), nullable=False),
    Column("recorded_by", String(ID), nullable=False),
    Column("command_id", String(ID), nullable=False),
    UniqueConstraint("asset_id", "sequence"),
)

maintenance_tasks = Table(
    "maintenance_tasks",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("item_type_id", String(ID), ForeignKey("item_types.id"), nullable=False),
    Column("name", String(80), nullable=False),
    Column("every_hours", String(16)),
    Column("every_cycles", Integer),
    Column("every_landings", Integer),
    Column("every_days", Integer),
    Column("tolerance_hours", String(16), nullable=False),
    Column("tolerance_cycles", Integer, nullable=False),
    Column("tolerance_landings", Integer, nullable=False),
    Column("tolerance_days", Integer, nullable=False),
    Column("life_limit", Boolean, nullable=False),
    Column("instructions", Text, nullable=False),
    Column("effective_from", String(10), nullable=False),
    Column("is_active", Boolean, nullable=False),
)

task_completions = Table(
    "task_completions",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("asset_id", String(ID), ForeignKey("assets.id"), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("task_id", String(ID), ForeignKey("maintenance_tasks.id"), nullable=False),
    Column("done_on", String(10), nullable=False),
    Column("meters", Text, nullable=False),  # JSON {meter: reading}
    Column("work_order_id", String(ID)),
    Column("notes", Text, nullable=False),
    Column("recorded_at", String(32), nullable=False),
    Column("recorded_by", String(ID), nullable=False),
    Column("command_id", String(ID), nullable=False),
    UniqueConstraint("asset_id", "sequence"),
)

defects = Table(
    "defects",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("number", String(16), nullable=False, unique=True),
    Column("asset_id", String(ID), ForeignKey("assets.id"), nullable=False, index=True),
    Column("description", Text, nullable=False),
    Column("reported_by", String(ID), nullable=False),
    Column("reported_at", String(32), nullable=False),
    Column("found_on", String(10), nullable=False),
    Column("state", String(16), nullable=False),
    Column("limitation", Text, nullable=False),
    Column("deferred_until", String(10)),
    Column("assessed_by", String(ID)),
    Column("assessed_at", String(32)),
    Column("assessment_note", Text, nullable=False),
    Column("work_order_id", String(ID)),
)

work_orders = Table(
    "work_orders",
    metadata,
    Column("id", String(ID), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("number", String(16), nullable=False, unique=True),
    Column("asset_id", String(ID), ForeignKey("assets.id"), nullable=False, index=True),
    Column("title", String(120), nullable=False),
    Column("task_ids", Text, nullable=False),
    Column("defect_ids", Text, nullable=False),
    Column("state", String(16), nullable=False),
    Column("opened_by", String(ID), nullable=False),
    Column("opened_at", String(32), nullable=False),
    Column("work_done", Text, nullable=False),
    Column("parts", Text, nullable=False),
    Column("completed_by", String(ID)),
    Column("completed_at", String(32)),
    Column("certified_by", String(ID)),
    Column("certified_at", String(32)),
    Column("note", Text, nullable=False),
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
