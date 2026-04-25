"""Persist generated candidate adapter metadata."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_generated_candidate_adapter_metadata"
down_revision: str | None = "0007_preview_audit_event_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_METADATA_COLUMNS: tuple[tuple[str, sa.String], ...] = (
    ("adapter_provider", sa.String(length=64)),
    ("adapter_model", sa.String(length=255)),
    ("adapter_version", sa.String(length=255)),
    ("adapter_run_id", sa.String(length=255)),
    ("prompt_version", sa.String(length=255)),
    ("prompt_fingerprint", sa.String(length=255)),
)


def upgrade() -> None:
    for name, column_type in _METADATA_COLUMNS:
        op.add_column("preview_candidates", sa.Column(name, column_type, nullable=True))
    for name, column_type in _METADATA_COLUMNS:
        op.add_column("preview_audit_events", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    for name, _column_type in reversed(_METADATA_COLUMNS):
        op.drop_column("preview_audit_events", name)
    for name, _column_type in reversed(_METADATA_COLUMNS):
        op.drop_column("preview_candidates", name)
