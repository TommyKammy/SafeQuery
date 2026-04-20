"""Baseline Alembic revision scaffold.

This intentionally establishes migration bookkeeping only. Domain tables are
introduced in later issues so future schema work can build on a stable
migration environment without restructuring it.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
