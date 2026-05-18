"""Persist Review LLM decision evidence."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0012_review_decision_persistence"
down_revision: str | None = "0011_semantic_contract_preview_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preview_review_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_decision_id", sa.String(length=255), nullable=False),
        sa.Column("preview_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("audit_event_id", sa.Uuid(), nullable=False),
        sa.Column("registered_source_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("source_flavor", sa.String(length=64), nullable=True),
        sa.Column("dataset_contract_version", sa.Integer(), nullable=False),
        sa.Column("semantic_contract_version", sa.String(length=255), nullable=True),
        sa.Column("schema_snapshot_version", sa.Integer(), nullable=False),
        sa.Column("review_contract_version", sa.String(length=255), nullable=False),
        sa.Column("review_status", sa.String(length=64), nullable=False),
        sa.Column("review_confidence", sa.String(length=32), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("risk_flags", sa.JSON(), nullable=False),
        sa.Column("clarifying_questions", sa.JSON(), nullable=False),
        sa.Column("review_payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            [
                "preview_candidate_id",
                "candidate_id",
                "request_id",
                "registered_source_id",
                "source_id",
                "source_family",
                "dataset_contract_version",
                "schema_snapshot_version",
            ],
            [
                "preview_candidates.id",
                "preview_candidates.candidate_id",
                "preview_candidates.request_id",
                "preview_candidates.registered_source_id",
                "preview_candidates.source_id",
                "preview_candidates.source_family",
                "preview_candidates.dataset_contract_version",
                "preview_candidates.schema_snapshot_version",
            ],
            name=op.f("fk_preview_review_decisions_preview_candidate_identity"),
        ),
        sa.ForeignKeyConstraint(
            ["audit_event_id"],
            ["preview_audit_events.event_id"],
            name=op.f("fk_preview_review_decisions_audit_event_id_preview_audit_events"),
        ),
        sa.ForeignKeyConstraint(
            ["registered_source_id"],
            ["registered_sources.id"],
            name=op.f(
                "fk_preview_review_decisions_registered_source_id_registered_sources"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preview_review_decisions")),
        sa.UniqueConstraint(
            "review_decision_id",
            name=op.f("uq_preview_review_decisions_review_decision_id"),
        ),
        sa.UniqueConstraint(
            "preview_candidate_id",
            name=op.f("uq_preview_review_decisions_preview_candidate_id"),
        ),
        sa.UniqueConstraint(
            "candidate_id",
            name=op.f("uq_preview_review_decisions_candidate_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("preview_review_decisions")
