from __future__ import annotations


VALID_GOVERNANCE_BINDING_TYPES = frozenset({"group", "role", "entitlement"})


def normalize_governance_binding(binding: str | None) -> str | None:
    if binding is None:
        return None

    trimmed = binding.strip()
    if not trimmed or ":" not in trimmed:
        return None

    binding_type, value = trimmed.split(":", 1)
    binding_type = binding_type.strip()
    value = value.strip()
    if (
        binding_type not in VALID_GOVERNANCE_BINDING_TYPES
        or not value
        or ":" in value
    ):
        return None

    return f"{binding_type}:{value}"
