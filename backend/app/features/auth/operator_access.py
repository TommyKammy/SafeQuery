from __future__ import annotations

from app.core.errors import api_error
from app.features.auth.context import AuthenticatedSubject


OPERATOR_EVIDENCE_READ_AUTHORITY_BINDINGS = frozenset(
    {
        "entitlement:safequery-admin",
        "entitlement:safequery-operator-evidence-read",
        "entitlement:safequery-support",
        "group:security-reviewers",
        "role:safequery-admin",
        "role:safequery-support",
        "role:sql-reviewer",
    }
)


def ensure_operator_evidence_read_authority(
    authenticated_subject: AuthenticatedSubject,
) -> None:
    subject_bindings = authenticated_subject.normalized_governance_bindings()
    if subject_bindings & OPERATOR_EVIDENCE_READ_AUTHORITY_BINDINGS:
        return

    raise api_error(
        403,
        "operator_read_forbidden",
        "Operator evidence requires reviewer or support authority.",
    )
