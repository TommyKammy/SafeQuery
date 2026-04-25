from __future__ import annotations

from typing import Literal, Mapping, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from typing_extensions import Annotated, Self

from app.features.audit.event_model import NonEmptyTrimmedString
from app.features.auth.context import AuthenticatedSubject
from app.features.auth.governance_bindings import normalize_governance_binding


BindingType = Literal["group", "role", "entitlement"]


class EnterpriseBridgeSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: NonEmptyTrimmedString
    idp_subject: Optional[NonEmptyTrimmedString] = None
    issuer: NonEmptyTrimmedString


class EnterpriseBridgeSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: NonEmptyTrimmedString
    issuer: NonEmptyTrimmedString


class EnterpriseGovernanceBindingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding_type: BindingType
    value: NonEmptyTrimmedString
    source_claim: NonEmptyTrimmedString

    @field_validator("value")
    @classmethod
    def reject_prequalified_binding_values(cls, value: str) -> str:
        if ":" in value:
            raise ValueError(
                "Governance binding value must be unqualified; "
                "binding_type supplies the namespace."
            )
        return value

    @property
    def normalized_binding(self) -> str:
        normalized = normalize_governance_binding(f"{self.binding_type}:{self.value}")
        if normalized is None:
            raise ValueError("Governance binding is malformed.")
        return normalized


class EnterpriseAuthBridgeInput(BaseModel):
    """Production-facing contract for a trusted enterprise identity bridge.

    The external bridge proves identity and supplies normalized governance hints.
    SafeQuery still owns session establishment and source entitlement decisions.
    Tokens, credentials, and IdP secrets are accepted only as redaction posture
    inputs and are excluded from all serialized contract and audit metadata.
    """

    model_config = ConfigDict(extra="forbid")

    bridge_source: NonEmptyTrimmedString
    subject: EnterpriseBridgeSubject
    session: EnterpriseBridgeSession
    governance_bindings: Annotated[
        list[EnterpriseGovernanceBindingInput],
        Field(min_length=1),
    ]
    raw_token: Optional[SecretStr] = Field(default=None, exclude=True)
    client_secret: Optional[SecretStr] = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def reject_duplicate_normalized_bindings(self) -> Self:
        seen: set[str] = set()
        for binding in self.governance_bindings:
            normalized = binding.normalized_binding
            if normalized in seen:
                raise ValueError(f"Duplicate governance binding: {normalized}")
            seen.add(normalized)
        return self


class SubjectProvenanceAuditMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issuer: NonEmptyTrimmedString
    idp_subject_present: bool


class BindingProvenanceAuditMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding: NonEmptyTrimmedString
    binding_type: BindingType
    source_claim: NonEmptyTrimmedString
    bridge_source: NonEmptyTrimmedString


class EnterpriseAuthBridgeAuditMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bridge_source: NonEmptyTrimmedString
    subject_id: NonEmptyTrimmedString
    session_id: NonEmptyTrimmedString
    subject_provenance: SubjectProvenanceAuditMetadata
    binding_provenance: list[BindingProvenanceAuditMetadata]


class EnterpriseAuthBridgeContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    authenticated_subject: AuthenticatedSubject
    session: EnterpriseBridgeSession
    audit_metadata: EnterpriseAuthBridgeAuditMetadata


def normalize_enterprise_auth_bridge_input(
    bridge_input: Mapping[str, object] | EnterpriseAuthBridgeInput,
) -> EnterpriseAuthBridgeContext:
    normalized_input = (
        bridge_input
        if isinstance(bridge_input, EnterpriseAuthBridgeInput)
        else EnterpriseAuthBridgeInput.model_validate(bridge_input)
    )
    bindings = [
        binding.normalized_binding
        for binding in normalized_input.governance_bindings
    ]

    return EnterpriseAuthBridgeContext(
        authenticated_subject=AuthenticatedSubject(
            subject_id=normalized_input.subject.subject_id,
            governance_bindings=frozenset(bindings),
        ),
        session=normalized_input.session,
        audit_metadata=EnterpriseAuthBridgeAuditMetadata(
            bridge_source=normalized_input.bridge_source,
            subject_id=normalized_input.subject.subject_id,
            session_id=normalized_input.session.session_id,
            subject_provenance=SubjectProvenanceAuditMetadata(
                issuer=normalized_input.subject.issuer,
                idp_subject_present=normalized_input.subject.idp_subject is not None,
            ),
            binding_provenance=[
                BindingProvenanceAuditMetadata(
                    binding=binding.normalized_binding,
                    binding_type=binding.binding_type,
                    source_claim=binding.source_claim,
                    bridge_source=normalized_input.bridge_source,
                )
                for binding in normalized_input.governance_bindings
            ],
        ),
    )
