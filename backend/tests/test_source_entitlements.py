import unittest
import uuid
from typing import Optional

from app.db.models.dataset_contract import DatasetContract
from app.db.models.source_registry import RegisteredSource
from app.features.auth.context import AuthenticatedSubject
from app.services.source_entitlements import SourceEntitlementError, ensure_subject_is_entitled_for_source


def _registered_source(*, source_id: str, activation_posture: str = "active") -> RegisteredSource:
    return RegisteredSource(
        id=uuid.uuid4(),
        source_id=source_id,
        display_label=source_id.replace("-", " ").title(),
        source_family="postgresql",
        source_flavor="warehouse",
        activation_posture=activation_posture,
        connector_profile_id=None,
        dialect_profile_id=None,
        dataset_contract_id=None,
        schema_snapshot_id=None,
        execution_policy_id=None,
        connection_reference=f"vault:{source_id}",
    )


def _dataset_contract(
    *,
    registered_source_id: uuid.UUID,
    owner_binding: Optional[str] = None,
    security_review_binding: Optional[str] = None,
    exception_policy_binding: Optional[str] = None,
) -> DatasetContract:
    return DatasetContract(
        id=uuid.uuid4(),
        registered_source_id=registered_source_id,
        schema_snapshot_id=uuid.uuid4(),
        contract_version=1,
        display_name="Approved vendor spend contract",
        owner_binding=owner_binding,
        security_review_binding=security_review_binding,
        exception_policy_binding=exception_policy_binding,
    )


class SourceEntitlementTestCase(unittest.TestCase):
    def test_subject_with_matching_source_binding_is_allowed(self) -> None:
        source = _registered_source(source_id="sap-approved-spend")
        contract = _dataset_contract(
            registered_source_id=source.id,
            owner_binding="group:finance-analysts",
        )
        subject = AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )

        resolved_source = ensure_subject_is_entitled_for_source(subject, source, contract)

        self.assertIs(resolved_source, source)

    def test_subject_with_matching_binding_after_contract_whitespace_normalization_is_allowed(self) -> None:
        source = _registered_source(source_id="sap-approved-spend")
        contract = _dataset_contract(
            registered_source_id=source.id,
            owner_binding=" group:finance-analysts ",
        )
        subject = AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )

        resolved_source = ensure_subject_is_entitled_for_source(subject, source, contract)

        self.assertIs(resolved_source, source)

    def test_subject_without_matching_source_binding_is_denied(self) -> None:
        source = _registered_source(source_id="sap-approved-spend")
        contract = _dataset_contract(
            registered_source_id=source.id,
            owner_binding="group:finance-approvers",
            security_review_binding="group:security-reviewers",
        )
        subject = AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )

        with self.assertRaisesRegex(
            SourceEntitlementError,
            "is not entitled to use registered source 'sap-approved-spend'",
        ):
            ensure_subject_is_entitled_for_source(subject, source, contract)

    def test_non_executable_source_posture_is_rejected_before_entitlement_allow(self) -> None:
        source = _registered_source(
            source_id="legacy-finance-archive",
            activation_posture="paused",
        )
        contract = _dataset_contract(
            registered_source_id=source.id,
            owner_binding="group:finance-analysts",
        )
        subject = AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )

        with self.assertRaisesRegex(
            SourceEntitlementError,
            "not executable while in paused posture",
        ):
            ensure_subject_is_entitled_for_source(subject, source, contract)


if __name__ == "__main__":
    unittest.main()
