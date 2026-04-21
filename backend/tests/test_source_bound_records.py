from app.features.auth.context import AuthenticatedSubject
from app.services.request_preview import (
    PreviewSubmissionRequest,
    submit_preview_request,
)


def test_preview_submission_binds_all_records_to_authoritative_source_id() -> None:
    response = submit_preview_request(
        PreviewSubmissionRequest(
            question="Show approved vendors by quarterly spend",
            source_id="sap-approved-spend",
        ),
        AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        ),
    )

    assert response.model_dump() == {
        "request": {
            "question": "Show approved vendors by quarterly spend",
            "source_id": "sap-approved-spend",
            "state": "submitted",
        },
        "candidate": {
            "source_id": "sap-approved-spend",
            "state": "preview_ready",
        },
        "audit": {
            "source_id": "sap-approved-spend",
            "state": "recorded",
        },
        "evaluation": {
            "source_id": "sap-approved-spend",
            "state": "pending",
        },
    }
