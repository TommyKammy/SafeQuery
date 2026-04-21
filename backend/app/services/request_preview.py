from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated
from typing import Optional

from app.db.models.dataset_contract import DatasetContract
from app.db.models.source_registry import RegisteredSource
from app.features.auth.context import AuthenticatedSubject
from app.services.source_entitlements import (
    SourceEntitlementError,
    ensure_subject_is_entitled_for_source,
)


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PreviewSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: NonEmptyTrimmedString
    source_id: NonEmptyTrimmedString


class RequestRecord(BaseModel):
    question: str
    source_id: str
    state: str


class CandidateRecord(BaseModel):
    source_id: str
    state: str


class AuditRecord(BaseModel):
    source_id: str
    state: str


class EvaluationRecord(BaseModel):
    source_id: str
    state: str


class PreviewSubmissionResponse(BaseModel):
    request: RequestRecord
    candidate: CandidateRecord
    audit: AuditRecord
    evaluation: EvaluationRecord


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


def _phase1_dataset_contract(
    *,
    source: RegisteredSource,
    owner_binding: Optional[str] = None,
    security_review_binding: Optional[str] = None,
    exception_policy_binding: Optional[str] = None,
) -> DatasetContract:
    return DatasetContract(
        id=uuid5(NAMESPACE_URL, f"safequery://dataset-contract/{source.source_id}/v1"),
        registered_source_id=source.id,
        schema_snapshot_id=uuid5(
            NAMESPACE_URL,
            f"safequery://schema-snapshot/{source.source_id}/v1",
        ),
        contract_version=1,
        display_name=f"{source.display_label} contract",
        owner_binding=owner_binding,
        security_review_binding=security_review_binding,
        exception_policy_binding=exception_policy_binding,
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

PHASE1_DATASET_CONTRACTS: dict[str, DatasetContract] = {
    "sap-approved-spend": _phase1_dataset_contract(
        source=PHASE1_REGISTERED_SOURCES["sap-approved-spend"],
        owner_binding="group:finance-analysts",
        security_review_binding="group:finance-reviewers",
    ),
    "legacy-finance-archive": _phase1_dataset_contract(
        source=PHASE1_REGISTERED_SOURCES["legacy-finance-archive"],
        owner_binding="group:archive-operators",
    ),
}


class PreviewSubmissionContractError(ValueError):
    """Raised when a preview submission does not carry an executable source binding."""


def submit_preview_request(
    payload: PreviewSubmissionRequest,
    authenticated_subject: AuthenticatedSubject,
) -> PreviewSubmissionResponse:
    source = PHASE1_REGISTERED_SOURCES.get(payload.source_id)
    if source is None:
        raise PreviewSubmissionContractError(
            f"Registered source '{payload.source_id}' does not exist."
        )

    try:
        resolved_source = ensure_subject_is_entitled_for_source(
            authenticated_subject,
            source,
            PHASE1_DATASET_CONTRACTS.get(payload.source_id),
        )
    except SourceEntitlementError as exc:
        raise PreviewSubmissionContractError(str(exc)) from exc

    return PreviewSubmissionResponse(
        request=RequestRecord(
            question=payload.question,
            source_id=resolved_source.source_id,
            state="submitted",
        ),
        candidate=CandidateRecord(
            source_id=resolved_source.source_id,
            state="preview_ready",
        ),
        audit=AuditRecord(
            source_id=resolved_source.source_id,
            state="recorded",
        ),
        evaluation=EvaluationRecord(
            source_id=resolved_source.source_id,
            state="pending",
        ),
    )
