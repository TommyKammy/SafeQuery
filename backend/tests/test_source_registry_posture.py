import unittest
import uuid

from app.db.models.source_registry import RegisteredSource
from app.services.source_registry import (
    SourceRegistryActivationGateError,
    SourceRegistryPostureError,
    ensure_source_is_executable,
)


class SourceRegistryPostureTestCase(unittest.TestCase):
    def test_only_active_sources_are_executable(self) -> None:
        active_source = RegisteredSource(
            id=uuid.uuid4(),
            source_id="finance-warehouse",
            display_label="Finance Warehouse",
            source_family="postgresql",
            source_flavor="warehouse",
            activation_posture="active",
            connector_profile_id=None,
            dialect_profile_id=None,
            dataset_contract_id=None,
            schema_snapshot_id=None,
            execution_policy_id=None,
            connection_reference="vault:finance-warehouse",
        )

        resolved_source = ensure_source_is_executable(active_source)

        self.assertIs(resolved_source, active_source)

    def test_non_executable_posture_is_rejected_fail_closed(self) -> None:
        for posture in ("paused", "blocked", "retired"):
            with self.subTest(posture=posture):
                source = RegisteredSource(
                    id=uuid.uuid4(),
                    source_id=f"{posture}-warehouse",
                    display_label=f"{posture.title()} Warehouse",
                    source_family="postgresql",
                    source_flavor=None,
                    activation_posture=posture,
                    connector_profile_id=None,
                    dialect_profile_id=None,
                    dataset_contract_id=None,
                    schema_snapshot_id=None,
                    execution_policy_id=None,
                    connection_reference=f"vault:{posture}-warehouse",
                )

                with self.assertRaisesRegex(
                    SourceRegistryPostureError,
                    f"{posture} posture",
                ):
                    ensure_source_is_executable(source)

    def test_planned_or_unsupported_active_sources_are_rejected_fail_closed(
        self,
    ) -> None:
        for source_id, source_family, source_flavor in (
            ("mysql-planned-ledger", "mysql", "mysql-8"),
            ("aurora-planned-ledger", "postgresql", "aurora-postgresql"),
            ("unsupported-ledger", "unsupported-family", "warehouse"),
        ):
            with self.subTest(source_id=source_id):
                source = RegisteredSource(
                    id=uuid.uuid4(),
                    source_id=source_id,
                    display_label=f"{source_id} display",
                    source_family=source_family,
                    source_flavor=source_flavor,
                    activation_posture="active",
                    connector_profile_id=None,
                    dialect_profile_id=None,
                    dataset_contract_id=None,
                    schema_snapshot_id=None,
                    execution_policy_id=None,
                    connection_reference=f"vault:{source_id}",
                )

                with self.assertRaisesRegex(
                    SourceRegistryActivationGateError,
                    "blocked posture",
                ):
                    ensure_source_is_executable(source)


if __name__ == "__main__":
    unittest.main()
