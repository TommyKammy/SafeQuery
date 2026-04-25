"""Add authoritative preview request and candidate records."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_preview_persistence"
down_revision: str | None = "0005_retrieval_corpus_scaffold"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preview_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("registered_source_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("source_flavor", sa.String(length=64), nullable=True),
        sa.Column("dataset_contract_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_contract_version", sa.Integer(), nullable=False),
        sa.Column("schema_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("schema_snapshot_version", sa.Integer(), nullable=False),
        sa.Column("authenticated_subject_id", sa.String(length=255), nullable=False),
        sa.Column("auth_source", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("governance_bindings", sa.Text(), nullable=True),
        sa.Column("entitlement_decision", sa.String(length=32), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("request_state", sa.String(length=64), nullable=False),
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
            ["registered_source_id"],
            ["registered_sources.id"],
            name=op.f("fk_preview_requests_registered_source_id_registered_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_contract_id"],
            ["dataset_contracts.id"],
            name=op.f("fk_preview_requests_dataset_contract_id_dataset_contracts"),
        ),
        sa.ForeignKeyConstraint(
            ["schema_snapshot_id"],
            ["schema_snapshots.id"],
            name=op.f("fk_preview_requests_schema_snapshot_id_schema_snapshots"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preview_requests")),
        sa.UniqueConstraint("request_id", name=op.f("uq_preview_requests_request_id")),
        sa.UniqueConstraint(
            "id",
            "registered_source_id",
            name=op.f("uq_preview_requests_id"),
        ),
    )
    op.create_table(
        "preview_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.String(length=255), nullable=False),
        sa.Column("preview_request_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("registered_source_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("source_flavor", sa.String(length=64), nullable=True),
        sa.Column("dataset_contract_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_contract_version", sa.Integer(), nullable=False),
        sa.Column("schema_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("schema_snapshot_version", sa.Integer(), nullable=False),
        sa.Column("authenticated_subject_id", sa.String(length=255), nullable=False),
        sa.Column("candidate_sql", sa.Text(), nullable=True),
        sa.Column("guard_status", sa.String(length=64), nullable=False),
        sa.Column("candidate_state", sa.String(length=64), nullable=False),
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
            ["preview_request_id"],
            ["preview_requests.id"],
            name=op.f("fk_preview_candidates_preview_request_id_preview_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["registered_source_id"],
            ["registered_sources.id"],
            name=op.f("fk_preview_candidates_registered_source_id_registered_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_contract_id"],
            ["dataset_contracts.id"],
            name=op.f("fk_preview_candidates_dataset_contract_id_dataset_contracts"),
        ),
        sa.ForeignKeyConstraint(
            ["schema_snapshot_id"],
            ["schema_snapshots.id"],
            name=op.f("fk_preview_candidates_schema_snapshot_id_schema_snapshots"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preview_candidates")),
        sa.UniqueConstraint(
            "candidate_id",
            name=op.f("uq_preview_candidates_candidate_id"),
        ),
        sa.UniqueConstraint(
            "request_id",
            "source_id",
            name=op.f("uq_preview_candidates_request_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("preview_candidates")
    op.drop_table("preview_requests")
