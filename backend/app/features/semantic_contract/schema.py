from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, MutableMapping, MutableSequence, MutableSet
from typing import Callable, Iterator, Literal, Optional, TypeVar, get_args, get_origin

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
SPEND_CONCEPT_PATTERN = re.compile(
    r"(?i)(?<!su)spen[dt][a-z0-9]*(?=$|[^a-z0-9])"
)
SemanticConceptT = TypeVar("SemanticConceptT")
SEMANTIC_CONTRACT_MODEL_CONFIG = ConfigDict(
    alias_generator=to_camel,
    extra="forbid",
    frozen=True,
    populate_by_name=True,
)


class _FrozenMapping(Mapping[SourceIdentifier, NonEmptyTrimmedString]):
    __slots__ = ("_values",)

    def __init__(
        self, values: Mapping[SourceIdentifier, NonEmptyTrimmedString]
    ) -> None:
        self._values = dict(values)

    def __getitem__(self, key: SourceIdentifier) -> NonEmptyTrimmedString:
        return self._values[key]

    def __iter__(self) -> Iterator[SourceIdentifier]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __deepcopy__(self, memo: dict[int, object]) -> "_FrozenMapping":
        copied = type(self)(self._values.copy())
        memo[id(self)] = copied
        return copied


def _annotation_allows_mutable_collection(annotation: object) -> bool:
    origin = get_origin(annotation)
    candidate = origin or annotation
    if _is_mutable_collection_type(candidate):
        return True
    return any(
        _annotation_allows_mutable_collection(arg)
        for arg in get_args(annotation)
        if arg is not Ellipsis
    )


def _is_mutable_collection_type(candidate: object) -> bool:
    try:
        return issubclass(candidate, (MutableMapping, MutableSequence, MutableSet))
    except TypeError:
        return False


class _SemanticContractModel(BaseModel):
    model_config = SEMANTIC_CONTRACT_MODEL_CONFIG

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        for field_name, field_info in cls.model_fields.items():
            if _annotation_allows_mutable_collection(field_info.annotation):
                raise TypeError(
                    f"{cls.__name__}.{field_name} must use immutable "
                    "collection annotations."
                )

    @model_validator(mode="after")
    def validate_immutable_collections(self) -> "_SemanticContractModel":
        for field_name in type(self).model_fields:
            _reject_mutable_collections(
                getattr(self, field_name),
                f"{type(self).__name__}.{field_name}",
            )
        return self


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
    locked: StrictBool = False

    @model_validator(mode="after")
    def validate_sources(self) -> "SemanticFilter":
        _require_non_empty_unique(self.allowed_source_ids, "Filter")
        return self


class SemanticTimeRange(_SemanticContractModel):
    default_grain: TimeGrain
    allowed_grains: tuple[TimeGrain, ...]
    requires_explicit_range: StrictBool

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
        default_factory=lambda: _FrozenMapping({})
    )

    def to_wire_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)

    @field_validator("ambiguity_rules", mode="after")
    @classmethod
    def freeze_ambiguity_rules(
        cls, value: Mapping[SourceIdentifier, NonEmptyTrimmedString]
    ) -> Mapping[SourceIdentifier, NonEmptyTrimmedString]:
        return _FrozenMapping(value)

    @field_serializer("ambiguity_rules")
    def serialize_ambiguity_rules(
        self, value: Mapping[SourceIdentifier, NonEmptyTrimmedString]
    ) -> dict[SourceIdentifier, NonEmptyTrimmedString]:
        return dict(value)

    @model_validator(mode="after")
    def validate_contract_references(self) -> "SemanticContractDefinition":
        source_ids, dimensions_by_id, filters_by_id = _index_contract_references(self)

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
            _require_metric_dimensions_compatible(metric, dimensions_by_id)
            _require_metric_default_filters_compatible(metric, filters_by_id)
            _require_subset(
                metric.time_range_semantics.allowed_grains,
                self.time_semantics.allowed_grains,
                f"Metric {metric.metric_id} references undeclared time grains",
            )

        for ambiguous_term in self.time_semantics.ambiguous_terms:
            if ambiguous_term not in self.ambiguity_rules:
                raise ValueError(
                    "Declared ambiguous terms must have matching ambiguity_rules."
                )
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
                metric.expression,
            ]
        )
    return any(_contains_spend_concept(term) for term in spend_terms)


def _contains_spend_concept(term: str) -> bool:
    return bool(SPEND_CONCEPT_PATTERN.search(term))


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


def _unique_concepts_by_id(
    concepts: Iterable[SemanticConceptT],
    get_id: Callable[[SemanticConceptT], SourceIdentifier],
    label: str,
) -> dict[SourceIdentifier, SemanticConceptT]:
    concepts_by_id: dict[SourceIdentifier, SemanticConceptT] = {}
    for concept in concepts:
        concept_id = get_id(concept)
        if concept_id in concepts_by_id:
            raise ValueError(f"{label} must not contain duplicate values.")
        concepts_by_id[concept_id] = concept
    return concepts_by_id


def _index_contract_references(
    contract: SemanticContractDefinition,
) -> tuple[
    set[SourceIdentifier],
    dict[SourceIdentifier, SemanticDimension],
    dict[SourceIdentifier, SemanticFilter],
]:
    source_ids = _unique_ids(
        [item.source_id for item in contract.source_bindings],
        "Contract source bindings",
    )
    dimensions_by_id = _unique_concepts_by_id(
        contract.dimensions,
        lambda item: item.dimension_id,
        "Contract dimensions",
    )
    filters_by_id = _unique_concepts_by_id(
        contract.filters,
        lambda item: item.filter_id,
        "Contract filters",
    )
    _unique_ids([item.metric_id for item in contract.metrics], "Contract metrics")
    _require_unique_sensitive_concepts(contract.sensitive_concepts)
    return source_ids, dimensions_by_id, filters_by_id


def _require_unique_sensitive_concepts(
    concepts: Iterable[SensitiveSemanticConcept],
) -> None:
    _unique_concepts_by_id(
        concepts,
        lambda item: item.concept_id,
        "Contract sensitive concepts",
    )


def _require_subset(
    values: Iterable[object],
    allowed_values: set[object],
    message: str,
) -> None:
    if not set(values).issubset(allowed_values):
        raise ValueError(message)


def _require_metric_dimensions_compatible(
    metric: SemanticMetric,
    dimensions_by_id: Mapping[SourceIdentifier, SemanticDimension],
) -> None:
    _require_subset(
        metric.allowed_dimensions,
        set(dimensions_by_id),
        f"Metric {metric.metric_id} references undeclared dimensions",
    )
    _require_referenced_concepts_share_metric_source(
        metric.allowed_source_ids,
        dimensions_by_id,
        metric.allowed_dimensions,
        _get_dimension_source_ids,
        (
            f"Metric {metric.metric_id} references dimensions without "
            "compatible allowed sources"
        ),
    )


def _require_metric_default_filters_compatible(
    metric: SemanticMetric,
    filters_by_id: Mapping[SourceIdentifier, SemanticFilter],
) -> None:
    _require_subset(
        metric.default_filters,
        set(filters_by_id),
        f"Metric {metric.metric_id} references undeclared default filters",
    )
    _require_referenced_concepts_share_metric_source(
        metric.allowed_source_ids,
        filters_by_id,
        metric.default_filters,
        _get_filter_source_ids,
        (
            f"Metric {metric.metric_id} references default filters without "
            "compatible allowed sources"
        ),
    )


def _get_dimension_source_ids(
    dimension: SemanticDimension,
) -> Iterable[SourceIdentifier]:
    return dimension.allowed_source_ids


def _get_filter_source_ids(
    semantic_filter: SemanticFilter,
) -> Iterable[SourceIdentifier]:
    return semantic_filter.allowed_source_ids


def _require_referenced_concepts_share_metric_source(
    metric_source_ids: Iterable[SourceIdentifier],
    concepts_by_id: Mapping[SourceIdentifier, SemanticConceptT],
    referenced_ids: Iterable[SourceIdentifier],
    get_source_ids: Callable[[SemanticConceptT], Iterable[SourceIdentifier]],
    message: str,
) -> None:
    common_source_ids = set(metric_source_ids)
    for referenced_id in referenced_ids:
        concept = concepts_by_id.get(referenced_id)
        if concept is None:
            raise ValueError(message)
        common_source_ids.intersection_update(set(get_source_ids(concept)))
        if not common_source_ids:
            raise ValueError(message)


def _reject_mutable_collections(value: object, path: str) -> None:
    if isinstance(value, (MutableMapping, MutableSequence, MutableSet)):
        raise ValueError(f"{path} must use immutable collections after validation.")

    if isinstance(value, _SemanticContractModel):
        for field_name in type(value).model_fields:
            _reject_mutable_collections(
                getattr(value, field_name),
                f"{path}.{field_name}",
            )
        return

    if isinstance(value, tuple):
        for index, item in enumerate(value):
            _reject_mutable_collections(item, f"{path}[{index}]")
        return

    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_mutable_collections(key, f"{path}.key")
            _reject_mutable_collections(item, f"{path}[{key!r}]")
