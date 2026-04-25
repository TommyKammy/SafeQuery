from collections.abc import Mapping
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

import psycopg

from app.core.config import SQLGenerationSettings


def check_database_health(database_url: str) -> Mapping[str, str]:
    try:
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except Exception as exc:  # pragma: no cover - exercised through stack smoke verification.
        return {
            "status": "error",
            "detail": exc.__class__.__name__,
        }

    return {
        "status": "ok",
        "detail": "ready",
    }


def _safe_endpoint(base_url: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _health_url(base_url: str) -> str:
    return f"{str(base_url).rstrip('/')}/health"


def check_sql_generation_runtime_health(
    settings: SQLGenerationSettings,
) -> Mapping[str, object]:
    base_payload: dict[str, object] = {
        "status": "disabled",
        "detail": "provider_disabled",
        "provider": settings.provider,
        "timeout_seconds": settings.timeout_seconds,
        "retry_count": settings.retry_count,
        "circuit_breaker_failure_threshold": (
            settings.circuit_breaker_failure_threshold
        ),
    }

    if settings.provider == "disabled":
        return base_payload

    if settings.provider != "local_llm":
        return {
            **base_payload,
            "status": "unchecked",
            "detail": "provider_health_probe_not_configured",
        }

    if settings.local_llm_base_url is None:
        return {
            **base_payload,
            "status": "error",
            "detail": "missing_endpoint",
        }

    endpoint = _safe_endpoint(str(settings.local_llm_base_url))
    payload = {
        **base_payload,
        "provider": "local_llm",
        "endpoint": endpoint,
    }
    request = Request(
        _health_url(str(settings.local_llm_base_url)),
        headers={"Accept": "application/json"},
        method="GET",
    )

    try:
        with urlopen(request, timeout=settings.timeout_seconds) as response:  # noqa: S310
            raw_body = response.read().decode("utf-8", errors="replace")
            status = getattr(response, "status", 200)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {
            **payload,
            "status": "error",
            "detail": exc.__class__.__name__,
        }

    runtime_status = None
    try:
        decoded = json.loads(raw_body)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, dict):
        runtime_status = decoded.get("status")

    if status >= 400 or runtime_status not in {"ok", "ready"}:
        return {
            **payload,
            "status": "error",
            "detail": "unhealthy_response",
        }

    return {
        **payload,
        "status": "ok",
        "detail": "ready",
    }
