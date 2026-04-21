from sqlalchemy import UniqueConstraint

from app.db.models.source_registry import RegisteredSource


def test_registered_source_scaffold_matches_minimum_shape() -> None:
    table = RegisteredSource.__table__

    assert table.name == "registered_sources"

    assert set(table.columns.keys()) == {
        "id",
        "source_id",
        "display_label",
        "source_family",
        "source_flavor",
        "activation_posture",
        "connector_profile_id",
        "dialect_profile_id",
        "dataset_contract_id",
        "schema_snapshot_id",
        "execution_policy_id",
        "connection_reference",
        "created_at",
        "updated_at",
    }

    assert table.c.source_id.nullable is False
    assert table.c.display_label.nullable is False
    assert table.c.source_family.nullable is False
    assert table.c.source_flavor.nullable is True
    assert table.c.activation_posture.nullable is False
    assert table.c.connector_profile_id.nullable is True
    assert table.c.dialect_profile_id.nullable is True
    assert table.c.dataset_contract_id.nullable is True
    assert table.c.schema_snapshot_id.nullable is True
    assert table.c.execution_policy_id.nullable is True
    assert table.c.connection_reference.nullable is False
    assert table.c.created_at.onupdate is None
    assert table.c.updated_at.onupdate is not None

    unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("source_id",) in unique_constraints
