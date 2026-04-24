from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.source_registry import RegisteredSource


class OperatorWorkflowSourceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(serialization_alias="sourceId")
    display_label: str = Field(serialization_alias="displayLabel")
    description: str
    activation_posture: str = Field(serialization_alias="activationPosture")
    source_family: str = Field(serialization_alias="sourceFamily")
    source_flavor: Optional[str] = Field(default=None, serialization_alias="sourceFlavor")


class OperatorWorkflowHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_type: Literal["request", "candidate", "run"] = Field(serialization_alias="itemType")
    record_id: str = Field(serialization_alias="recordId")
    label: str
    source_id: str = Field(serialization_alias="sourceId")
    source_label: str = Field(serialization_alias="sourceLabel")
    lifecycle_state: str = Field(serialization_alias="lifecycleState")
    occurred_at: datetime = Field(serialization_alias="occurredAt")
    guard_status: Optional[str] = Field(default=None, serialization_alias="guardStatus")
    run_state: Optional[str] = Field(default=None, serialization_alias="runState")


class OperatorWorkflowSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[OperatorWorkflowSourceOption]
    history: list[OperatorWorkflowHistoryItem] = Field(default_factory=list)


def _source_description(source: RegisteredSource) -> str:
    flavor = f" / {source.source_flavor}" if source.source_flavor else ""
    return (
        f"{source.source_family}{flavor} source with "
        f"{source.activation_posture.value} activation posture."
    )


def get_operator_workflow_snapshot(session: Session) -> OperatorWorkflowSnapshot:
    sources = (
        session.execute(select(RegisteredSource).order_by(RegisteredSource.source_id))
        .scalars()
        .all()
    )

    source_options = [
        OperatorWorkflowSourceOption(
            source_id=source.source_id,
            display_label=source.display_label,
            description=_source_description(source),
            activation_posture=source.activation_posture.value,
            source_family=source.source_family,
            source_flavor=source.source_flavor,
        )
        for source in sources
    ]

    return OperatorWorkflowSnapshot(sources=source_options, history=[])
