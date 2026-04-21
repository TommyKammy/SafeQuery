from __future__ import annotations

from app.db.models.source_registry import RegisteredSource, SourceActivationPosture


class SourceRegistryPostureError(RuntimeError):
    """Raised when a source is not executable under its current registry posture."""


def ensure_source_is_executable(source: RegisteredSource) -> RegisteredSource:
    posture = SourceActivationPosture(source.activation_posture)
    if posture.is_executable:
        return source

    raise SourceRegistryPostureError(
        f"Registered source '{source.source_id}' is not executable while in "
        f"{posture.value} posture."
    )
