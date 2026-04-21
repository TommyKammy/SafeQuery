from __future__ import annotations

from app.db.models.dataset_contract import DatasetContract
from app.db.models.source_registry import RegisteredSource
from app.features.auth.context import AuthenticatedSubject
from app.services.source_registry import (
    SourceRegistryPostureError,
    ensure_source_is_executable,
)


class SourceEntitlementError(PermissionError):
    """Raised when a subject is not entitled to use a selected registered source."""


def _contract_governance_bindings(contract: DatasetContract) -> frozenset[str]:
    bindings = {
        binding
        for binding in (
            contract.owner_binding,
            contract.security_review_binding,
            contract.exception_policy_binding,
        )
        if binding is not None and binding.strip()
    }
    return frozenset(bindings)


def ensure_subject_is_entitled_for_source(
    subject: AuthenticatedSubject,
    source: RegisteredSource,
    dataset_contract: DatasetContract | None,
) -> RegisteredSource:
    try:
        resolved_source = ensure_source_is_executable(source)
    except (SourceRegistryPostureError, ValueError) as exc:
        raise SourceEntitlementError(str(exc)) from exc

    if dataset_contract is None or dataset_contract.registered_source_id != resolved_source.id:
        raise SourceEntitlementError(
            f"Registered source '{resolved_source.source_id}' is missing "
            "authoritative source-scoped governance artifacts."
        )

    source_bindings = _contract_governance_bindings(dataset_contract)
    if not source_bindings:
        raise SourceEntitlementError(
            f"Registered source '{resolved_source.source_id}' has no "
            "source-scoped governance bindings."
        )

    subject_bindings = subject.normalized_governance_bindings()
    if not subject_bindings:
        raise SourceEntitlementError(
            f"Authenticated subject '{subject.normalized_subject_id()}' has no "
            "trusted governance bindings."
        )

    if subject_bindings.isdisjoint(source_bindings):
        raise SourceEntitlementError(
            f"Authenticated subject '{subject.normalized_subject_id()}' is not "
            f"entitled to use registered source '{resolved_source.source_id}'."
        )

    return resolved_source
