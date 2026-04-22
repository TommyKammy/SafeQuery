from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError
from typing_extensions import Annotated


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SQLGuardSourceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: NonEmptyTrimmedString
    source_family: NonEmptyTrimmedString
    source_flavor: Optional[NonEmptyTrimmedString] = None


class SQLGuardEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_sql: NonEmptyTrimmedString
    source: SQLGuardSourceBinding


class SQLGuardRejection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["invalid_contract"]
    detail: NonEmptyTrimmedString
    path: NonEmptyTrimmedString


class SQLGuardEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "reject"]
    profile: Literal["common"]
    canonical_sql: Optional[str]
    source: Optional[SQLGuardSourceBinding]
    rejections: list[SQLGuardRejection]


def _contract_rejections(exc: ValidationError) -> list[SQLGuardRejection]:
    return [
        SQLGuardRejection(
            code="invalid_contract",
            detail=error["msg"],
            path=".".join(str(segment) for segment in error["loc"]),
        )
        for error in exc.errors()
    ]


def evaluate_common_sql_guard(
    payload: Union[SQLGuardEvaluationInput, dict[str, Any]],
) -> SQLGuardEvaluation:
    try:
        request = (
            payload
            if isinstance(payload, SQLGuardEvaluationInput)
            else SQLGuardEvaluationInput.model_validate(payload)
        )
    except ValidationError as exc:
        return SQLGuardEvaluation(
            decision="reject",
            profile="common",
            canonical_sql=None,
            source=None,
            rejections=_contract_rejections(exc),
        )

    return SQLGuardEvaluation(
        decision="allow",
        profile="common",
        canonical_sql=request.canonical_sql,
        source=request.source,
        rejections=[],
    )
