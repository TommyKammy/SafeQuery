"""Persist semantic contract version on preview lifecycle records."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0011_semantic_contract_preview_version"
down_revision: str | None = "0010_preview_revision_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dataset_contracts",
        sa.Column("semantic_contract_version", sa.String(length=255), nullable=True),
    )
    for table_name in ("preview_requests", "preview_candidates", "preview_audit_events"):
        op.add_column(
            table_name,
            sa.Column("semantic_contract_version", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    for table_name in ("preview_audit_events", "preview_candidates", "preview_requests"):
        op.drop_column(table_name, "semantic_contract_version")
    op.drop_column("dataset_contracts", "semantic_contract_version")
