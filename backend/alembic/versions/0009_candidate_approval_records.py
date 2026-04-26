"""Persist candidate approval and execute eligibility records."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_candidate_approval_records"
down_revision: str | None = "0008_generated_candidate_adapter_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preview_candidate_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.String(length=255), nullable=False),
        sa.Column("preview_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("registered_source_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("source_flavor", sa.String(length=64), nullable=True),
        sa.Column("dataset_contract_version", sa.Integer(), nullable=False),
        sa.Column("schema_snapshot_version", sa.Integer(), nullable=False),
        sa.Column("owner_subject_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_state", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["preview_candidate_id"],
            ["preview_candidates.id"],
            name=op.f(
                "fk_preview_candidate_approvals_preview_candidate_id_preview_candidates"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["registered_source_id"],
            ["registered_sources.id"],
            name=op.f(
                "fk_preview_candidate_approvals_registered_source_id_registered_sources"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preview_candidate_approvals")),
        sa.UniqueConstraint(
            "approval_id",
            name=op.f("uq_preview_candidate_approvals_approval_id"),
        ),
        sa.UniqueConstraint(
            "preview_candidate_id",
            name=op.f("uq_preview_candidate_approvals_preview_candidate_id"),
        ),
        sa.UniqueConstraint(
            "candidate_id",
            name=op.f("uq_preview_candidate_approvals_candidate_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("preview_candidate_approvals")
