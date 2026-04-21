"""Add the per-source dataset contract scaffold.

This revision adds application-owned dataset contract records that belong to one
registered business source at a time and carry source-scoped allow-listed
dataset entries.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_dataset_contract_scaffold"
down_revision: str | None = "0002_source_registry_scaffold"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

dataset_contract_dataset_kind = sa.Enum(
    "view",
    "table",
    "materialized_view",
    name="dataset_contract_dataset_kind",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "dataset_contracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("registered_source_id", sa.Uuid(), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("owner_binding", sa.String(length=255), nullable=True),
        sa.Column("security_review_binding", sa.String(length=255), nullable=True),
        sa.Column("exception_policy_binding", sa.String(length=255), nullable=True),
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
            name=op.f(
                "fk_dataset_contracts_registered_source_id_registered_sources"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_contracts")),
        sa.UniqueConstraint(
            "registered_source_id",
            "contract_version",
            name=op.f("uq_dataset_contracts_registered_source_id"),
        ),
    )
    op.create_table(
        "dataset_contract_datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_contract_id", sa.Uuid(), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column(
            "dataset_kind",
            dataset_contract_dataset_kind,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dataset_contract_id"],
            ["dataset_contracts.id"],
            name=op.f(
                "fk_dataset_contract_datasets_dataset_contract_id_dataset_contracts"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_contract_datasets")),
        sa.UniqueConstraint(
            "dataset_contract_id",
            "schema_name",
            "dataset_name",
            name=op.f("uq_dataset_contract_datasets_dataset_contract_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("dataset_contract_datasets")
    op.drop_table("dataset_contracts")
