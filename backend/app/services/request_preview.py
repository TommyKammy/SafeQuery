from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated
from typing import Optional

from app.db.models.source_registry import RegisteredSource
from app.services.source_registry import (
    SourceRegistryPostureError,
    ensure_source_is_executable,
)


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PreviewSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: NonEmptyTrimmedString
    source_id: NonEmptyTrimmedString


class PreviewSubmissionResponse(BaseModel):
    request: dict[str, str]
    candidate: dict[str, str]


def _phase1_registered_source(
    *,
    source_id: str,
    display_label: str,
    activation_posture: str,
    source_family: str = "postgresql",
    source_flavor: Optional[str] = None,
) -> RegisteredSource:
    return RegisteredSource(
        id=uuid5(NAMESPACE_URL, f"safequery://registered-source/{source_id}"),
        source_id=source_id,
        display_label=display_label,
        source_family=source_family,
        source_flavor=source_flavor,
        activation_posture=activation_posture,
        connector_profile_id=None,
        dialect_profile_id=None,
        dataset_contract_id=None,
        schema_snapshot_id=None,
        execution_policy_id=None,
        connection_reference=f"vault:{source_id}",
    )


PHASE1_REGISTERED_SOURCES: dict[str, RegisteredSource] = {
    "sap-approved-spend": _phase1_registered_source(
        source_id="sap-approved-spend",
        display_label="SAP spend cube / approved_vendor_spend",
        activation_posture="active",
        source_flavor="warehouse",
    ),
    "legacy-finance-archive": _phase1_registered_source(
        source_id="legacy-finance-archive",
        display_label="Legacy finance archive",
        activation_posture="paused",
        source_flavor="archive",
    ),
}


class PreviewSubmissionContractError(ValueError):
    """Raised when a preview submission does not carry an executable source binding."""


def submit_preview_request(
    payload: PreviewSubmissionRequest,
) -> PreviewSubmissionResponse:
    source = PHASE1_REGISTERED_SOURCES.get(payload.source_id)
    if source is None:
        raise PreviewSubmissionContractError(
            f"Registered source '{payload.source_id}' does not exist."
        )

    try:
        resolved_source = ensure_source_is_executable(source)
    except SourceRegistryPostureError as exc:
        raise PreviewSubmissionContractError(str(exc)) from exc

    return PreviewSubmissionResponse(
        request={
            "question": payload.question,
            "source_id": resolved_source.source_id,
            "state": "submitted",
        },
        candidate={
            "source_id": resolved_source.source_id,
            "state": "preview_ready",
        },
    )
