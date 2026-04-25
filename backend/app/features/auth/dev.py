from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.features.auth.context import AuthenticatedSubject
from app.services.demo_source_seed import (
    DEMO_DEV_GOVERNANCE_BINDING,
    DEMO_DEV_SUBJECT_ID,
)


def build_dev_authenticated_subject() -> AuthenticatedSubject:
    return AuthenticatedSubject(
        subject_id=DEMO_DEV_SUBJECT_ID,
        governance_bindings=frozenset({DEMO_DEV_GOVERNANCE_BINDING}),
    )


async def attach_dev_authenticated_subject(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request.state.authenticated_subject = build_dev_authenticated_subject()
    return await call_next(request)
