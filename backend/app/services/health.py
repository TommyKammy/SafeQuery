from collections import Counter
from collections.abc import Mapping
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

import psycopg
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import SQLGenerationSettings
from app.db.models.dataset_contract import DatasetContract
from app.db.models.preview import PreviewAuditEvent
from app.db.models.schema_snapshot import SchemaSnapshot
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.execution import (
    ExecutionConnectorSelectionError,
    select_execution_connector,
)
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


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


def _component_status(component: Mapping[str, object]) -> str:
    status = component.get("status")
    return status if isinstance(status, str) else "error"


def _aggregate_operator_status(
    components: Mapping[str, Mapping[str, object]],
) -> str:
    statuses = {_component_status(component) for component in components.values()}
    if "error" in statuses:
        return "error"
    if statuses - {"ok", "disabled", "unchecked"}:
        return "degraded"
    return "ok"


def _backend_component(database: Mapping[str, str]) -> dict[str, object]:
    if database.get("status") != "ok":
        return {"status": "error", "detail": "database_unavailable"}
    return {"status": "ok", "detail": "ready"}


def _generation_adapter_component(
    sql_generation: Mapping[str, object],
) -> dict[str, object]:
    status = sql_generation.get("status")
    detail = sql_generation.get("detail")
    provider = sql_generation.get("provider")
    return {
        "status": status if isinstance(status, str) else "error",
        "detail": detail if isinstance(detail, str) else "malformed_health_payload",
        "provider": provider if isinstance(provider, str) else "unknown",
    }


def _source_registry_component(
    sources: list[RegisteredSource],
) -> dict[str, object]:
    postures = {
        posture.value: sum(
            1 for source in sources if source.activation_posture is posture
        )
        for posture in SourceActivationPosture
    }
    active_source_count = postures[SourceActivationPosture.ACTIVE.value]
    return {
        "status": "ok" if active_source_count > 0 else "degraded",
        "detail": "ready" if active_source_count > 0 else "no_active_sources",
        "registered_source_count": len(sources),
        "active_source_count": active_source_count,
        "postures": postures,
    }


def _source_has_backend_owned_connector(session: Session, source: RegisteredSource) -> bool:
    if source.dataset_contract_id is None or source.schema_snapshot_id is None:
        return False
    contract = session.get(DatasetContract, source.dataset_contract_id)
    snapshot = session.get(SchemaSnapshot, source.schema_snapshot_id)
    if contract is None or snapshot is None:
        return False

    try:
        select_execution_connector(
            candidate_source=SourceBoundCandidateMetadata(
                source_id=source.source_id,
                source_family=source.source_family,
                source_flavor=source.source_flavor,
                dataset_contract_version=contract.contract_version,
                schema_snapshot_version=snapshot.snapshot_version,
            )
        )
    except ExecutionConnectorSelectionError:
        return False
    return True


def _active_source_connectivity_component(
    session: Session,
    sources: list[RegisteredSource],
) -> dict[str, object]:
    active_sources = [
        source
        for source in sources
        if source.activation_posture is SourceActivationPosture.ACTIVE
    ]
    ready_source_count = sum(
        1
        for source in active_sources
        if _source_has_backend_owned_connector(session, source)
    )
    unavailable_source_count = len(active_sources) - ready_source_count
    if not active_sources:
        status = "degraded"
        detail = "no_active_sources"
    elif unavailable_source_count:
        status = "degraded"
        detail = "active_source_connector_unavailable"
    else:
        status = "ok"
        detail = "ready"

    return {
        "status": status,
        "detail": detail,
        "active_source_count": len(active_sources),
        "ready_source_count": ready_source_count,
        "unavailable_source_count": unavailable_source_count,
    }


def _audit_persistence_component(session: Session) -> dict[str, object]:
    session.scalar(select(func.count()).select_from(PreviewAuditEvent))
    return {"status": "ok", "detail": "ready"}


def _bounded_counts(counter: Counter[str], *, limit: int = 8) -> dict[str, int]:
    return {
        key: count
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[
            :limit
        ]
    }


def _terminal_failure_key(event: PreviewAuditEvent) -> str:
    for value in (
        event.denial_cause,
        event.primary_deny_code,
        event.candidate_state,
        event.event_type,
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def _workflow_lifecycle_metrics(session: Session) -> dict[str, object]:
    events = list(
        session.scalars(
            select(PreviewAuditEvent).order_by(
                PreviewAuditEvent.event_type,
                PreviewAuditEvent.source_id,
            )
        )
    )
    event_count = len(events)
    preview_terminal_failures: Counter[str] = Counter()
    execute_terminal_failures: Counter[str] = Counter()
    source_ids: set[str] = set()

    metrics: dict[str, object] = {
        "status": "active" if event_count else "no_traffic",
        "audit_event_count": event_count,
        "preview": {
            "submitted": 0,
            "generation_completed": 0,
            "generation_failed": 0,
            "guard_evaluated": 0,
            "terminal_failures": {},
        },
        "execute": {
            "requested": 0,
            "completed": 0,
            "denied": 0,
            "failed": 0,
            "terminal_failures": {},
        },
        "audit_persistence": {
            "recorded_events": event_count,
            "sources_with_events": 0,
        },
    }
    preview = metrics["preview"]
    execute = metrics["execute"]
    assert isinstance(preview, dict)
    assert isinstance(execute, dict)

    for event in events:
        source_ids.add(event.source_id)
        if event.event_type == "query_submitted":
            preview["submitted"] = int(preview["submitted"]) + 1
        elif event.event_type == "generation_completed":
            preview["generation_completed"] = int(preview["generation_completed"]) + 1
        elif event.event_type == "generation_failed":
            preview["generation_failed"] = int(preview["generation_failed"]) + 1
            preview_terminal_failures[_terminal_failure_key(event)] += 1
        elif event.event_type == "guard_evaluated":
            preview["guard_evaluated"] = int(preview["guard_evaluated"]) + 1
        elif event.event_type == "execution_requested":
            execute["requested"] = int(execute["requested"]) + 1
        elif event.event_type == "execution_completed":
            execute["completed"] = int(execute["completed"]) + 1
        elif event.event_type == "execution_denied":
            execute["denied"] = int(execute["denied"]) + 1
            execute_terminal_failures[_terminal_failure_key(event)] += 1
        elif event.event_type == "execution_failed":
            execute["failed"] = int(execute["failed"]) + 1
            execute_terminal_failures[_terminal_failure_key(event)] += 1

    preview["terminal_failures"] = _bounded_counts(preview_terminal_failures)
    execute["terminal_failures"] = _bounded_counts(execute_terminal_failures)
    audit_persistence = metrics["audit_persistence"]
    assert isinstance(audit_persistence, dict)
    audit_persistence["sources_with_events"] = len(source_ids)
    return metrics


def build_operator_health(
    session: Session,
    *,
    database: Mapping[str, str],
    sql_generation: Mapping[str, object],
) -> dict[str, object]:
    components: dict[str, dict[str, object]] = {
        "backend": _backend_component(database),
        "frontend_api_connection": {"status": "ok", "detail": "reachable"},
        "generation_adapter": _generation_adapter_component(sql_generation),
    }

    try:
        sources = list(
            session.scalars(select(RegisteredSource).order_by(RegisteredSource.source_id))
        )
        components["source_registry"] = _source_registry_component(sources)
        components["active_source_connectivity"] = (
            _active_source_connectivity_component(session, sources)
        )
        components["audit_persistence"] = _audit_persistence_component(session)
        workflow_lifecycle_metrics = _workflow_lifecycle_metrics(session)
    except SQLAlchemyError as exc:
        detail = {"status": "error", "detail": exc.__class__.__name__}
        components["source_registry"] = detail
        components["active_source_connectivity"] = {
            "status": "error",
            "detail": "source_registry_unavailable",
        }
        components["audit_persistence"] = {
            "status": "error",
            "detail": "audit_persistence_unavailable",
        }
        workflow_lifecycle_metrics = {
            "status": "error",
            "detail": "audit_persistence_unavailable",
        }

    return {
        "status": _aggregate_operator_status(components),
        "can_authorize_execution": False,
        "components": components,
        "workflow_lifecycle_metrics": workflow_lifecycle_metrics,
    }
