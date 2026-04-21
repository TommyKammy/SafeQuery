from sqlalchemy import UniqueConstraint

from app.db.models.dataset_contract import DatasetContract, DatasetContractDataset


def test_dataset_contracts_are_scoped_to_one_registered_source() -> None:
    table = DatasetContract.__table__

    assert table.name == "dataset_contracts"
    assert set(table.columns.keys()) == {
        "id",
        "registered_source_id",
        "contract_version",
        "display_name",
        "owner_binding",
        "security_review_binding",
        "exception_policy_binding",
        "created_at",
        "updated_at",
    }

    assert table.c.registered_source_id.nullable is False
    assert table.c.contract_version.nullable is False
    assert table.c.display_name.nullable is False
    assert table.c.owner_binding.nullable is True
    assert table.c.security_review_binding.nullable is True
    assert table.c.exception_policy_binding.nullable is True
    assert table.c.created_at.onupdate is None
    assert table.c.updated_at.onupdate is not None

    unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("registered_source_id", "contract_version") in unique_constraints

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


def test_allowlisted_datasets_are_bound_to_one_contract_version() -> None:
    table = DatasetContractDataset.__table__

    assert table.name == "dataset_contract_datasets"
    assert set(table.columns.keys()) == {
        "id",
        "dataset_contract_id",
        "schema_name",
        "dataset_name",
        "dataset_kind",
        "created_at",
    }

    assert table.c.dataset_contract_id.nullable is False
    assert table.c.schema_name.nullable is False
    assert table.c.dataset_name.nullable is False
    assert table.c.dataset_kind.nullable is False

    unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert (
        "dataset_contract_id",
        "schema_name",
        "dataset_name",
    ) in unique_constraints

    foreign_keys = {
        (
            foreign_key.parent.name,
            foreign_key.column.table.name,
            foreign_key.column.name,
        )
        for foreign_key in table.foreign_keys
    }

    assert foreign_keys == {
        ("dataset_contract_id", "dataset_contracts", "id"),
    }


def test_dataset_contract_model_stays_separate_from_application_postgres_role() -> None:
    contract_columns = DatasetContract.__table__.columns.keys()
    dataset_columns = DatasetContractDataset.__table__.columns.keys()

    for name in ("app_postgres_url", "application_postgres_identity"):
        assert name not in contract_columns
        assert name not in dataset_columns
