"""Persist preview revision context."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0010_preview_revision_context"
down_revision: str | None = "0009_candidate_approval_records"
branch_labels: str | None = None
depends_on: str | None = None


_REVISION_COLUMNS = (
    ("revised_from_request_id", sa.String(length=255)),
    ("revised_from_candidate_id", sa.String(length=255)),
    ("revised_from_run_id", sa.String(length=255)),
    ("revised_from_source_id", sa.String(length=255)),
)


def upgrade() -> None:
    for table_name in ("preview_requests", "preview_candidates"):
        for column_name, column_type in _REVISION_COLUMNS:
            op.add_column(table_name, sa.Column(column_name, column_type, nullable=True))


def downgrade() -> None:
    for table_name in ("preview_candidates", "preview_requests"):
        for column_name, _ in reversed(_REVISION_COLUMNS):
            op.drop_column(table_name, column_name)
