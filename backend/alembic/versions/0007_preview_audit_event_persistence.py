"""Persist preview lifecycle audit events."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_preview_audit_event_persistence"
down_revision: str | None = "0006_preview_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preview_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("lifecycle_order", sa.Integer(), nullable=False),
        sa.Column("preview_request_id", sa.Uuid(), nullable=False),
        sa.Column("preview_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("candidate_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("causation_event_id", sa.Uuid(), nullable=True),
        sa.Column("authenticated_subject_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("auth_source", sa.String(length=255), nullable=True),
        sa.Column("governance_bindings", sa.Text(), nullable=True),
        sa.Column("entitlement_decision", sa.String(length=32), nullable=True),
        sa.Column("entitlement_source_bindings", sa.Text(), nullable=True),
        sa.Column("application_version", sa.String(length=255), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("source_flavor", sa.String(length=64), nullable=True),
        sa.Column("dataset_contract_version", sa.Integer(), nullable=True),
        sa.Column("schema_snapshot_version", sa.Integer(), nullable=True),
        sa.Column("primary_deny_code", sa.String(length=255), nullable=True),
        sa.Column("denial_cause", sa.String(length=255), nullable=True),
        sa.Column("candidate_state", sa.String(length=64), nullable=True),
        sa.Column("audit_payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["preview_request_id"],
            ["preview_requests.id"],
            name=op.f("fk_preview_audit_events_preview_request_id_preview_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["preview_candidate_id"],
            ["preview_candidates.id"],
            name=op.f("fk_preview_audit_events_preview_candidate_id_preview_candidates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preview_audit_events")),
        sa.UniqueConstraint("event_id", name=op.f("uq_preview_audit_events_event_id")),
    )


def downgrade() -> None:
    op.drop_table("preview_audit_events")
