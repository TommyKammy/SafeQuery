from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request

from app.core.errors import api_error
from app.features.auth.governance_bindings import normalize_governance_binding


@dataclass(frozen=True)
class AuthenticatedSubject:
    subject_id: str
    governance_bindings: frozenset[str] = field(default_factory=frozenset)

    def normalized_subject_id(self) -> str:
        normalized = self.subject_id.strip()
        if not normalized:
            raise api_error(
                401,
                "unauthenticated",
                "Sign in before submitting preview requests.",
            )
        return normalized

    def normalized_governance_bindings(self) -> frozenset[str]:
        normalized_bindings = {
            normalized
            for binding in self.governance_bindings
            if (normalized := normalize_governance_binding(binding)) is not None
        }
        return frozenset(normalized_bindings)


def require_authenticated_subject(request: Request) -> AuthenticatedSubject:
    subject = getattr(request.state, "authenticated_subject", None)
    if not isinstance(subject, AuthenticatedSubject):
        raise api_error(
            401,
            "unauthenticated",
            "Sign in before submitting preview requests.",
        )

    return AuthenticatedSubject(
        subject_id=subject.normalized_subject_id(),
        governance_bindings=subject.normalized_governance_bindings(),
    )
