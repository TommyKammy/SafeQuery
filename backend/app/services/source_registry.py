from __future__ import annotations

from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.services.source_family_profiles import (
    ACTIVE_SOURCE_FAMILIES,
    get_planned_source_family_profile_requirements,
    get_planned_source_flavor_profile_requirements,
)


class SourceRegistryPostureError(RuntimeError):
    """Raised when a source is not executable under its current registry posture."""


class SourceRegistryActivationGateError(SourceRegistryPostureError):
    """Raised when rollout metadata blocks source execution."""


def effective_source_activation_posture(
    source: RegisteredSource,
) -> SourceActivationPosture:
    posture = SourceActivationPosture(source.activation_posture)
    if posture is not SourceActivationPosture.ACTIVE:
        return posture

    source_family = source.source_family.strip().lower()
    source_flavor = (
        source.source_flavor.strip().lower() if source.source_flavor else None
    )
    planned_family = get_planned_source_family_profile_requirements(source_family)
    planned_flavor = (
        get_planned_source_flavor_profile_requirements(
            source_family=source_family,
            source_flavor=source_flavor,
        )
        if source_flavor is not None
        else None
    )
    if (
        source_family not in ACTIVE_SOURCE_FAMILIES
        or planned_family is not None
        or planned_flavor is not None
    ):
        return SourceActivationPosture.BLOCKED

    return posture


def ensure_source_is_executable(source: RegisteredSource) -> RegisteredSource:
    posture = SourceActivationPosture(source.activation_posture)
    effective_posture = effective_source_activation_posture(source)
    if posture.is_executable and effective_posture.is_executable:
        return source

    error_class = (
        SourceRegistryActivationGateError
        if posture.is_executable and effective_posture is SourceActivationPosture.BLOCKED
        else SourceRegistryPostureError
    )
    raise error_class(
        f"Registered source '{source.source_id}' is not executable while in "
        f"{effective_posture.value} posture."
    )
