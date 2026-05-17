from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    StrictBool,
    field_serializer,
    field_validator,
    model_validator,
)

from app.features.audit.event_model import (
    NonEmptyTrimmedString,
    SourceFamily,
    SourceFlavor,
    SourceIdentifier,
    to_camel,
)

SemanticContractStatus = Literal["draft", "active", "retired"]
TimeGrain = Literal[
    "day",
    "week",
    "month",
    "calendar_quarter",
    "fiscal_quarter",
    "year",
]
TimeRangePolicy = Literal["required", "optional", "clarify_when_unspecified"]


class _SemanticContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )


class SemanticContractVersionMetadata(_SemanticContractModel):
    identifier: SourceIdentifier
    version: PositiveInt
    status: SemanticContractStatus
    owner: SourceIdentifier
    created_for_issue: Optional[PositiveInt] = None


class SemanticSourceBinding(_SemanticContractModel):
    source_id: SourceIdentifier
    source_family: SourceFamily
    source_flavor: Optional[SourceFlavor] = None
    dataset_contract_version: PositiveInt
    schema_snapshot_version: PositiveInt


class SemanticDimension(_SemanticContractModel):
    dimension_id: SourceIdentifier
    label: NonEmptyTrimmedString
    source_column: NonEmptyTrimmedString
    allowed_source_ids: tuple[SourceIdentifier, ...]

    @model_validator(mode="after")
    def validate_sources(self) -> "SemanticDimension":
        _require_non_empty_unique(self.allowed_source_ids, "Dimension")
        return self


class SemanticFilter(_SemanticContractModel):
    filter_id: SourceIdentifier
    label: NonEmptyTrimmedString
    expression: NonEmptyTrimmedString
    allowed_source_ids: tuple[SourceIdentifier, ...]
    locked: bool = False

    @model_validator(mode="after")
    def validate_sources(self) -> "SemanticFilter":
        _require_non_empty_unique(self.allowed_source_ids, "Filter")
        return self


class SemanticTimeRange(_SemanticContractModel):
    default_grain: TimeGrain
    allowed_grains: tuple[TimeGrain, ...]
    requires_explicit_range: bool

    @model_validator(mode="after")
    def validate_default_grain(self) -> "SemanticTimeRange":
        _require_non_empty_unique(self.allowed_grains, "Time range")
        if self.default_grain not in self.allowed_grains:
            raise ValueError(
                "Time range default grain must be one of the allowed time grains."
            )
        return self


class SemanticMetric(_SemanticContractModel):
    metric_id: SourceIdentifier
    label: NonEmptyTrimmedString
    expression_owner: SourceIdentifier
    expression: NonEmptyTrimmedString
    allowed_source_ids: tuple[SourceIdentifier, ...]
    allowed_dimensions: tuple[SourceIdentifier, ...] = Field(default_factory=tuple)
    default_filters: tuple[SourceIdentifier, ...] = Field(default_factory=tuple)
    time_range_semantics: SemanticTimeRange

    @model_validator(mode="after")
    def validate_sources(self) -> "SemanticMetric":
        _require_non_empty_unique(self.allowed_source_ids, "Metric")
        _require_unique(self.allowed_dimensions, "Metric allowed dimensions")
        _require_unique(self.default_filters, "Metric default filters")
        return self


class SemanticContractTimeSemantics(_SemanticContractModel):
    default_grain: TimeGrain
    allowed_grains: tuple[TimeGrain, ...]
    ambiguous_terms: tuple[SourceIdentifier, ...] = Field(default_factory=tuple)
    range_policy: TimeRangePolicy

    @model_validator(mode="after")
    def validate_default_grain(self) -> "SemanticContractTimeSemantics":
        _require_non_empty_unique(self.allowed_grains, "Contract time semantics")
        _require_unique(self.ambiguous_terms, "Contract ambiguous time terms")
        if self.default_grain not in self.allowed_grains:
            raise ValueError(
                "Contract default grain must be one of the allowed time grains."
            )
        return self


class SensitiveSemanticConcept(_SemanticContractModel):
    concept_id: SourceIdentifier
    label: NonEmptyTrimmedString
    reason: NonEmptyTrimmedString
    requires_review: StrictBool

    @field_validator("requires_review")
    @classmethod
    def validate_requires_review(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Sensitive concepts must require review.")
        return value


class SemanticContractDefinition(_SemanticContractModel):
    contract_id: SourceIdentifier
    domain: SourceIdentifier
    version: SemanticContractVersionMetadata
    source_bindings: tuple[SemanticSourceBinding, ...]
    dimensions: tuple[SemanticDimension, ...] = Field(default_factory=tuple)
    filters: tuple[SemanticFilter, ...] = Field(default_factory=tuple)
    metrics: tuple[SemanticMetric, ...]
    time_semantics: SemanticContractTimeSemantics
    sensitive_concepts: tuple[SensitiveSemanticConcept, ...] = Field(
        default_factory=tuple
    )
    ambiguity_rules: Mapping[SourceIdentifier, NonEmptyTrimmedString] = Field(
        default_factory=lambda: MappingProxyType({})
    )

    def to_wire_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)

    @field_validator("ambiguity_rules", mode="after")
    @classmethod
    def freeze_ambiguity_rules(
        cls, value: Mapping[SourceIdentifier, NonEmptyTrimmedString]
    ) -> Mapping[SourceIdentifier, NonEmptyTrimmedString]:
        return MappingProxyType(dict(value))

    @field_serializer("ambiguity_rules")
    def serialize_ambiguity_rules(
        self, value: Mapping[SourceIdentifier, NonEmptyTrimmedString]
    ) -> dict[SourceIdentifier, NonEmptyTrimmedString]:
        return dict(value)

    @model_validator(mode="after")
    def validate_contract_references(self) -> "SemanticContractDefinition":
        source_ids = _unique_ids(
            [item.source_id for item in self.source_bindings],
            "Contract source bindings",
        )
        dimension_ids = _unique_ids(
            [item.dimension_id for item in self.dimensions],
            "Contract dimensions",
        )
        filter_ids = _unique_ids(
            [item.filter_id for item in self.filters],
            "Contract filters",
        )
        _unique_ids([item.metric_id for item in self.metrics], "Contract metrics")

        if not source_ids:
            raise ValueError("Contract must declare at least one allowed source.")
        if not self.metrics:
            raise ValueError("Contract must declare at least one metric.")

        for dimension in self.dimensions:
            _require_subset(
                dimension.allowed_source_ids,
                source_ids,
                (
                    f"Dimension {dimension.dimension_id} references undeclared "
                    "allowed sources"
                ),
            )

        for semantic_filter in self.filters:
            _require_subset(
                semantic_filter.allowed_source_ids,
                source_ids,
                (
                    f"Filter {semantic_filter.filter_id} references undeclared "
                    "allowed sources"
                ),
            )

        for metric in self.metrics:
            _require_subset(
                metric.allowed_source_ids,
                source_ids,
                f"Metric {metric.metric_id} references undeclared allowed sources",
            )
            _require_subset(
                metric.allowed_dimensions,
                dimension_ids,
                f"Metric {metric.metric_id} references undeclared dimensions",
            )
            _require_subset(
                metric.default_filters,
                filter_ids,
                f"Metric {metric.metric_id} references undeclared default filters",
            )
            _require_subset(
                metric.time_range_semantics.allowed_grains,
                self.time_semantics.allowed_grains,
                f"Metric {metric.metric_id} references undeclared time grains",
            )

        if (
            "quarter" in self.time_semantics.ambiguous_terms
            and "quarter" not in self.ambiguity_rules
        ):
            raise ValueError("Quarter ambiguity must be explicit in ambiguity_rules.")
        if (
            _contract_requires_spend_definition(self)
            and "spend_definition" not in self.ambiguity_rules
        ):
            raise ValueError(
                "Spend definition ambiguity must be explicit in ambiguity_rules."
            )

        return self


def validate_semantic_contract_definition(
    payload: dict[str, object],
) -> SemanticContractDefinition:
    return SemanticContractDefinition.model_validate(payload)


def _contract_requires_spend_definition(contract: SemanticContractDefinition) -> bool:
    spend_terms = [
        contract.contract_id,
        contract.domain,
    ]
    for dimension in contract.dimensions:
        spend_terms.extend(
            [dimension.dimension_id, dimension.label, dimension.source_column]
        )
    for semantic_filter in contract.filters:
        spend_terms.extend(
            [
                semantic_filter.filter_id,
                semantic_filter.label,
                semantic_filter.expression,
            ]
        )
    for metric in contract.metrics:
        spend_terms.extend(
            [
                metric.metric_id,
                metric.label,
                metric.expression_owner,
                metric.expression,
            ]
        )
    return any("spend" in term.lower() for term in spend_terms)


def _require_unique(values: Iterable[object], label: str) -> None:
    values_tuple = tuple(values)
    if len(set(values_tuple)) != len(values_tuple):
        raise ValueError(f"{label} must not contain duplicate values.")


def _require_non_empty_unique(values: Iterable[object], label: str) -> None:
    values_tuple = tuple(values)
    if not values_tuple:
        raise ValueError(f"{label} must declare at least one allowed source.")
    _require_unique(values_tuple, label)


def _unique_ids(
    values: Iterable[SourceIdentifier], label: str
) -> set[SourceIdentifier]:
    _require_unique(values, label)
    return set(values)


def _require_subset(
    values: Iterable[object],
    allowed_values: set[object],
    message: str,
) -> None:
    if not set(values).issubset(allowed_values):
        raise ValueError(message)
