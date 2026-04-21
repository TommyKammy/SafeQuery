from sqlalchemy import UniqueConstraint

from app.db.models.dataset_contract import DatasetContract
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource


def test_schema_snapshots_are_scoped_to_one_registered_source() -> None:
    table = SchemaSnapshot.__table__

    assert table.name == "schema_snapshots"
    assert set(table.columns.keys()) == {
        "id",
        "registered_source_id",
        "snapshot_version",
        "review_status",
        "reviewed_at",
        "captured_at",
        "created_at",
        "updated_at",
    }

    assert table.c.registered_source_id.nullable is False
    assert table.c.snapshot_version.nullable is False
    assert table.c.review_status.nullable is False
    assert table.c.reviewed_at.nullable is True
    assert table.c.captured_at.nullable is False
    assert table.c.created_at.onupdate is None
    assert table.c.updated_at.onupdate is not None
    assert tuple(table.c.review_status.type.enums) == (
        SchemaSnapshotReviewStatus.PENDING.value,
        SchemaSnapshotReviewStatus.APPROVED.value,
        SchemaSnapshotReviewStatus.REJECTED.value,
        SchemaSnapshotReviewStatus.SUPERSEDED.value,
    )

    unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("registered_source_id", "snapshot_version") in unique_constraints
    assert ("registered_source_id", "id") in unique_constraints

    foreign_keys = {
        (
            foreign_key.parent.name,
            foreign_key.column.table.name,
            foreign_key.column.name,
        )
        for foreign_key in table.foreign_keys
    }

    assert foreign_keys == {
        ("registered_source_id", "registered_sources", "id"),
    }


def test_dataset_contracts_bind_to_one_source_scoped_schema_snapshot() -> None:
    table = DatasetContract.__table__

    assert "schema_snapshot_id" in table.columns
    assert table.c.schema_snapshot_id.nullable is False

    foreign_keys = {
        (
            foreign_key.parent.name,
            foreign_key.column.table.name,
            foreign_key.column.name,
        )
        for foreign_key in table.foreign_keys
    }

    assert ("registered_source_id", "registered_sources", "id") in foreign_keys
    assert ("schema_snapshot_id", "schema_snapshots", "id") in foreign_keys

    composite_foreign_keys = {
        (
            tuple(element.parent.name for element in constraint.elements),
            tuple(element.column.table.name for element in constraint.elements),
            tuple(element.column.name for element in constraint.elements),
        )
        for constraint in table.foreign_key_constraints
    }

    assert (
        ("registered_source_id", "schema_snapshot_id"),
        ("schema_snapshots", "schema_snapshots"),
        ("registered_source_id", "id"),
    ) in composite_foreign_keys


def test_registered_source_links_active_contract_and_snapshot_without_cross_source_drift() -> None:
    table = RegisteredSource.__table__

    composite_foreign_keys = {
        (
            tuple(element.parent.name for element in constraint.elements),
            tuple(element.column.table.name for element in constraint.elements),
            tuple(element.column.name for element in constraint.elements),
        )
        for constraint in table.foreign_key_constraints
    }

    assert (
        ("id", "dataset_contract_id"),
        ("dataset_contracts", "dataset_contracts"),
        ("registered_source_id", "id"),
    ) in composite_foreign_keys
    assert (
        ("id", "schema_snapshot_id"),
        ("schema_snapshots", "schema_snapshots"),
        ("registered_source_id", "id"),
    ) in composite_foreign_keys
