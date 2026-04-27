from __future__ import annotations

from app.core.config import Settings
from app.core.errors import api_error
from app.features.auth.context import AuthenticatedSubject
from app.services.demo_source_seed import (
    DEMO_DEV_GOVERNANCE_BINDING,
    DEMO_DEV_SUBJECT_ID,
)


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


def _has_operator_evidence_read_authority(
    authenticated_subject: AuthenticatedSubject,
) -> bool:
    subject_bindings = authenticated_subject.normalized_governance_bindings()
    return bool(subject_bindings & OPERATOR_EVIDENCE_READ_AUTHORITY_BINDINGS)


def _has_local_dev_operator_workflow_authority(
    authenticated_subject: AuthenticatedSubject,
    settings: Settings,
) -> bool:
    if (
        not settings.dev_auth_enabled
        or settings.environment not in {"development", "test"}
    ):
        return False

    return (
        authenticated_subject.normalized_subject_id() == DEMO_DEV_SUBJECT_ID
        and DEMO_DEV_GOVERNANCE_BINDING
        in authenticated_subject.normalized_governance_bindings()
    )


def ensure_operator_evidence_read_authority(
    authenticated_subject: AuthenticatedSubject,
) -> None:
    if _has_operator_evidence_read_authority(authenticated_subject):
        return

    raise api_error(
        403,
        "operator_read_forbidden",
        "Operator evidence requires reviewer or support authority.",
    )


def ensure_operator_workflow_read_authority(
    authenticated_subject: AuthenticatedSubject,
    settings: Settings,
) -> None:
    if _has_operator_evidence_read_authority(
        authenticated_subject
    ) or _has_local_dev_operator_workflow_authority(authenticated_subject, settings):
        return

    raise api_error(
        403,
        "operator_read_forbidden",
        "Operator evidence requires reviewer or support authority.",
    )
