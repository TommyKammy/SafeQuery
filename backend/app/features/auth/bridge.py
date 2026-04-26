from __future__ import annotations

import re
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
IdentityClaimType = Literal["human_user", "service_account", "workload"]
MappingState = Literal["valid", "stale", "missing", "ambiguous", "unsupported"]


_WORKSTATION_LOCAL_PATH_RE = re.compile(
    r"(^|\s)(/Users/[^/\s]+/|/home/[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)"
)
_SECRET_MARKERS = frozenset(
    {"-----begin", "client_secret", "password", "private_key", "secret=", "token="}
)


def _reject_unsafe_evidence_text(value: str) -> str:
    if _WORKSTATION_LOCAL_PATH_RE.search(value):
        raise ValueError(
            "Enterprise mapping evidence must not contain workstation-local paths."
        )

    lowered = value.lower()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        raise ValueError(
            "Enterprise mapping evidence must not contain secrets or credentials."
        )
    return value


class EnterpriseBridgeActor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: NonEmptyTrimmedString
    actor_type: IdentityClaimType
    issuer: NonEmptyTrimmedString


class EnterpriseBridgeSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: NonEmptyTrimmedString
    subject_type: IdentityClaimType
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
    mapping_state: MappingState = "valid"
    mapping_evidence: Optional["EnterpriseGovernanceMappingEvidence"] = None

    @field_validator("value")
    @classmethod
    def reject_prequalified_binding_values(cls, value: str) -> str:
        if ":" in value:
            raise ValueError(
                "Governance binding value must be unqualified; "
                "binding_type supplies the namespace."
            )
        return value

    @model_validator(mode="after")
    def require_verifiable_current_mapping(self) -> Self:
        if self.mapping_state != "valid":
            raise ValueError(
                "Enterprise governance mapping is "
                f"{self.mapping_state}; explicit review is required before "
                "SafeQuery can grant application authority."
            )

        if self.mapping_evidence is None:
            raise ValueError(
                "Enterprise governance mapping evidence is missing; explicit "
                "review is required before SafeQuery can grant application authority."
            )
        return self

    @property
    def normalized_binding(self) -> str:
        normalized = normalize_governance_binding(f"{self.binding_type}:{self.value}")
        if normalized is None:
            raise ValueError("Governance binding is malformed.")
        return normalized


class EnterpriseGovernanceMappingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_issuer: NonEmptyTrimmedString
    claim_value_fingerprint: NonEmptyTrimmedString
    mapping_rule_id: NonEmptyTrimmedString
    review_state: NonEmptyTrimmedString

    @field_validator(
        "claim_issuer",
        "claim_value_fingerprint",
        "mapping_rule_id",
        "review_state",
    )
    @classmethod
    def reject_unsafe_evidence_text(cls, value: str) -> str:
        return _reject_unsafe_evidence_text(value)


class EnterpriseAuthBridgeInput(BaseModel):
    """Production-facing contract for a trusted enterprise identity bridge.

    The external bridge proves identity and supplies normalized governance hints.
    SafeQuery still owns session establishment and source entitlement decisions.
    Tokens, credentials, and IdP secrets are accepted only as redaction posture
    inputs and are excluded from all serialized contract and audit metadata.
    """

    model_config = ConfigDict(extra="forbid")

    bridge_source: NonEmptyTrimmedString
    actor: EnterpriseBridgeActor
    subject: EnterpriseBridgeSubject
    session: EnterpriseBridgeSession
    governance_bindings: Annotated[
        list[EnterpriseGovernanceBindingInput],
        Field(min_length=1),
    ]
    raw_token: Optional[SecretStr] = Field(default=None, exclude=True)
    client_secret: Optional[SecretStr] = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def reject_incoherent_claims_and_duplicate_normalized_bindings(self) -> Self:
        if self.actor.actor_id != self.subject.subject_id:
            raise ValueError(
                "Production identity bridge actor must match subject before "
                "SafeQuery can grant application authority."
            )

        if self.actor.actor_type != self.subject.subject_type:
            raise ValueError(
                "Production identity bridge actor type must match subject type "
                "before SafeQuery can grant application authority."
            )

        if self.actor.issuer != self.subject.issuer:
            raise ValueError(
                "Production identity bridge actor issuer must match subject issuer "
                "before SafeQuery can grant application authority."
            )

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
    mapping_state: MappingState
    mapping_evidence: EnterpriseGovernanceMappingEvidence


class EnterpriseAuthBridgeAuditMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bridge_source: NonEmptyTrimmedString
    actor_id: NonEmptyTrimmedString
    actor_type: IdentityClaimType
    subject_id: NonEmptyTrimmedString
    subject_type: IdentityClaimType
    session_id: NonEmptyTrimmedString
    subject_provenance: SubjectProvenanceAuditMetadata
    binding_provenance: list[BindingProvenanceAuditMetadata]


class ProductionIdentityClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: EnterpriseBridgeActor
    subject: EnterpriseBridgeSubject


class EnterpriseAuthBridgeContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    authenticated_subject: AuthenticatedSubject
    identity_claims: ProductionIdentityClaims
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
        identity_claims=ProductionIdentityClaims(
            actor=normalized_input.actor,
            subject=normalized_input.subject,
        ),
        session=normalized_input.session,
        audit_metadata=EnterpriseAuthBridgeAuditMetadata(
            bridge_source=normalized_input.bridge_source,
            actor_id=normalized_input.actor.actor_id,
            actor_type=normalized_input.actor.actor_type,
            subject_id=normalized_input.subject.subject_id,
            subject_type=normalized_input.subject.subject_type,
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
                    mapping_state=binding.mapping_state,
                    mapping_evidence=binding.mapping_evidence,
                )
                for binding in normalized_input.governance_bindings
            ],
        ),
    )
