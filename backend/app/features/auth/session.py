from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError
from typing_extensions import Annotated

from app.core.config import Settings, get_settings
from app.features.auth.context import AuthenticatedSubject, require_authenticated_subject


APPLICATION_SESSION_COOKIE = "safequery_session"
CSRF_HEADER = "x-safequery-csrf"
DEV_SESSION_SIGNING_KEY = "safequery-development-session-boundary-key"
_PLACEHOLDER_SIGNING_KEYS = {
    "change-me",
    "changeme",
    "dev-secret",
    "password",
    "secret",
    "test",
    "todo",
}
_SESSION_VERSION = 1
_DEFAULT_TTL = timedelta(hours=8)

NonEmptyTrimmedString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class ApplicationSessionClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    session_id: NonEmptyTrimmedString
    subject_id: NonEmptyTrimmedString
    governance_bindings: list[NonEmptyTrimmedString]
    csrf_token_hash: NonEmptyTrimmedString
    issued_at: int
    expires_at: int
    auth_source: NonEmptyTrimmedString


@dataclass(frozen=True)
class ApplicationSessionContext:
    """Validated application-owned session boundary for state-changing routes.

    Development auth and future production bridge inputs establish identity first.
    This context then proves that the browser/API request also carries a coherent
    SafeQuery session and matching CSRF token. Entitlement checks still happen
    after this boundary against authoritative source governance records.
    """

    subject_id: str
    governance_bindings: frozenset[str]
    auth_source: str

    @property
    def audit_session_id(self) -> str:
        return "application-session-redacted"


@dataclass(frozen=True)
class TestApplicationSession:
    cookie_name: str
    cookie_value: str
    csrf_header_name: str
    csrf_token: str

    @property
    def cookies(self) -> dict[str, str]:
        return {self.cookie_name: self.cookie_value}

    @property
    def headers(self) -> dict[str, str]:
        return {self.csrf_header_name: self.csrf_token}


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _session_signing_key(settings: Settings) -> bytes:
    if settings.session_signing_key:
        signing_key = settings.session_signing_key.get_secret_value().strip()
        if (
            settings.environment not in {"development", "test"}
            and (
                len(signing_key) < 32
                or signing_key.lower() in _PLACEHOLDER_SIGNING_KEYS
            )
        ):
            raise HTTPException(
                status_code=403,
                detail="Application session signing key is not trusted.",
            )
        return signing_key.encode("utf-8")

    if settings.dev_auth_enabled and settings.environment in {"development", "test"}:
        return DEV_SESSION_SIGNING_KEY.encode("utf-8")

    raise HTTPException(
        status_code=403,
        detail="Application session signing key is required.",
    )


def _csrf_token_hash(csrf_token: str) -> str:
    return hashlib.sha256(csrf_token.encode("utf-8")).hexdigest()


def _sign_payload(payload: dict[str, Any], *, signing_key: bytes) -> str:
    encoded_payload = _b64encode(_canonical_json(payload))
    signature = hmac.new(
        signing_key,
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64encode(signature)}"


def _decode_signed_payload(token: str, *, signing_key: bytes) -> dict[str, Any]:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            signing_key,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        supplied_signature = _b64decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise ValueError("signature mismatch")

        payload = json.loads(_b64decode(encoded_payload))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=403,
            detail="Application session context is malformed.",
        ) from None

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=403,
            detail="Application session context is malformed.",
        )
    return payload


def create_test_application_session(
    authenticated_subject: AuthenticatedSubject,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    ttl: timedelta = _DEFAULT_TTL,
    auth_source: str = "test-helper",
    csrf_token: str | None = None,
) -> TestApplicationSession:
    settings = settings or get_settings()
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    expires_at = current_time + ttl
    csrf_token = csrf_token or secrets.token_urlsafe(32)
    payload = {
        "version": _SESSION_VERSION,
        "session_id": secrets.token_urlsafe(32),
        "subject_id": authenticated_subject.normalized_subject_id(),
        "governance_bindings": sorted(
            authenticated_subject.normalized_governance_bindings()
        ),
        "csrf_token_hash": _csrf_token_hash(csrf_token),
        "issued_at": int(current_time.timestamp()),
        "expires_at": int(expires_at.timestamp()),
        "auth_source": auth_source,
    }
    return TestApplicationSession(
        cookie_name=APPLICATION_SESSION_COOKIE,
        cookie_value=_sign_payload(
            payload,
            signing_key=_session_signing_key(settings),
        ),
        csrf_header_name=CSRF_HEADER,
        csrf_token=csrf_token,
    )


def require_application_session(
    request: Request,
    authenticated_subject: AuthenticatedSubject = Depends(require_authenticated_subject),
) -> ApplicationSessionContext:
    settings = get_settings()
    session_cookie = request.cookies.get(APPLICATION_SESSION_COOKIE)
    csrf_token = request.headers.get(CSRF_HEADER)
    if not session_cookie or not csrf_token:
        raise HTTPException(
            status_code=403,
            detail="Application session and CSRF context are required.",
        )

    payload = _decode_signed_payload(
        session_cookie,
        signing_key=_session_signing_key(settings),
    )
    try:
        claims = ApplicationSessionClaims.model_validate(payload)
    except ValidationError:
        raise HTTPException(
            status_code=403,
            detail="Application session context is malformed.",
        ) from None

    if claims.version != _SESSION_VERSION:
        raise HTTPException(
            status_code=403,
            detail="Application session context is malformed.",
        )

    now = int(datetime.now(timezone.utc).timestamp())
    if claims.issued_at > now or claims.expires_at <= claims.issued_at:
        raise HTTPException(
            status_code=403,
            detail="Application session context is malformed.",
        )

    if claims.expires_at <= now:
        raise HTTPException(
            status_code=403,
            detail="Application session context is expired.",
        )

    subject_id = authenticated_subject.normalized_subject_id()
    governance_bindings = authenticated_subject.normalized_governance_bindings()
    if claims.subject_id != subject_id:
        raise HTTPException(
            status_code=403,
            detail="Application session subject does not match authenticated subject.",
        )

    session_bindings = frozenset(claims.governance_bindings)
    if session_bindings != governance_bindings:
        raise HTTPException(
            status_code=403,
            detail="Application session governance context does not match.",
        )

    if not hmac.compare_digest(claims.csrf_token_hash, _csrf_token_hash(csrf_token)):
        raise HTTPException(
            status_code=403,
            detail="Application session CSRF context does not match.",
        )

    return ApplicationSessionContext(
        subject_id=subject_id,
        governance_bindings=session_bindings,
        auth_source=claims.auth_source,
    )
