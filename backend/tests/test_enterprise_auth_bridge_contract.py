from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.features.auth.bridge import normalize_enterprise_auth_bridge_input


def _mapping_evidence(rule_id: str, review_state: str = "current") -> dict[str, str]:
    return {
        "claim_issuer": "https://idp.example.test",
        "claim_value_fingerprint": f"sha256:{rule_id}",
        "mapping_rule_id": rule_id,
        "review_state": review_state,
    }


def _valid_bridge_payload() -> dict[str, object]:
    return {
        "bridge_source": "saml-oidc-bridge",
        "actor": {
            "actor_id": " user:alice@example.com ",
            "actor_type": "human_user",
            "issuer": "https://idp.example.test",
        },
        "subject": {
            "subject_id": " user:alice@example.com ",
            "subject_type": "human_user",
            "idp_subject": "00u-enterprise-alice",
            "issuer": "https://idp.example.test",
        },
        "session": {
            "session_id": " session-123 ",
            "issuer": "https://idp.example.test",
        },
        "governance_bindings": [
            {
                "binding_type": "group",
                "value": " finance-analysts ",
                "source_claim": "groups",
                "mapping_state": "valid",
                "mapping_evidence": _mapping_evidence("rule-finance-analysts-v1"),
            },
            {
                "binding_type": "role",
                "value": " sql-reviewer ",
                "source_claim": "roles",
                "mapping_state": "valid",
                "mapping_evidence": _mapping_evidence("rule-sql-reviewer-v1"),
            },
        ],
        "raw_token": "<bridge-token-redacted>",
        "client_secret": "<client-secret-redacted>",
    }


class EnterpriseAuthBridgeContractTestCase(unittest.TestCase):
    def test_valid_bridge_input_normalizes_subject_session_and_bindings(self) -> None:
        context = normalize_enterprise_auth_bridge_input(_valid_bridge_payload())

        self.assertEqual(
            context.authenticated_subject.normalized_subject_id(),
            "user:alice@example.com",
        )
        self.assertEqual(
            context.identity_claims.actor.actor_id,
            "user:alice@example.com",
        )
        self.assertEqual(context.identity_claims.actor.actor_type, "human_user")
        self.assertEqual(
            context.identity_claims.subject.subject_id,
            "user:alice@example.com",
        )
        self.assertEqual(context.identity_claims.subject.subject_type, "human_user")
        self.assertEqual(context.session.session_id, "session-123")
        self.assertEqual(
            context.authenticated_subject.normalized_governance_bindings(),
            frozenset({"group:finance-analysts", "role:sql-reviewer"}),
        )
        self.assertEqual(
            context.audit_metadata.model_dump(),
            {
                "bridge_source": "saml-oidc-bridge",
                "actor_id": "user:alice@example.com",
                "actor_type": "human_user",
                "subject_id": "user:alice@example.com",
                "subject_type": "human_user",
                "session_id": "session-123",
                "subject_provenance": {
                    "issuer": "https://idp.example.test",
                    "idp_subject_present": True,
                },
                "binding_provenance": [
                    {
                        "binding": "group:finance-analysts",
                        "binding_type": "group",
                        "source_claim": "groups",
                        "bridge_source": "saml-oidc-bridge",
                        "mapping_state": "valid",
                        "mapping_evidence": {
                            "claim_issuer": "https://idp.example.test",
                            "claim_value_fingerprint": (
                                "sha256:rule-finance-analysts-v1"
                            ),
                            "mapping_rule_id": "rule-finance-analysts-v1",
                            "review_state": "current",
                        },
                    },
                    {
                        "binding": "role:sql-reviewer",
                        "binding_type": "role",
                        "source_claim": "roles",
                        "bridge_source": "saml-oidc-bridge",
                        "mapping_state": "valid",
                        "mapping_evidence": {
                            "claim_issuer": "https://idp.example.test",
                            "claim_value_fingerprint": "sha256:rule-sql-reviewer-v1",
                            "mapping_rule_id": "rule-sql-reviewer-v1",
                            "review_state": "current",
                        },
                    },
                ],
            },
        )

    def test_valid_enterprise_mapping_produces_typed_binding_evidence(self) -> None:
        payload = _valid_bridge_payload()
        payload["governance_bindings"] = [
            {
                "binding_type": "group",
                "value": "finance-analysts",
                "source_claim": "groups",
                "mapping_state": "valid",
                "mapping_evidence": {
                    "claim_issuer": "https://idp.example.test",
                    "claim_value_fingerprint": "sha256:finance-analysts",
                    "mapping_rule_id": "rule-finance-analysts-v1",
                    "review_state": "current",
                },
            }
        ]

        context = normalize_enterprise_auth_bridge_input(payload)

        self.assertEqual(
            context.authenticated_subject.normalized_governance_bindings(),
            frozenset({"group:finance-analysts"}),
        )
        self.assertEqual(
            context.audit_metadata.binding_provenance[0].model_dump(),
            {
                "binding": "group:finance-analysts",
                "binding_type": "group",
                "source_claim": "groups",
                "bridge_source": "saml-oidc-bridge",
                "mapping_state": "valid",
                "mapping_evidence": {
                    "claim_issuer": "https://idp.example.test",
                    "claim_value_fingerprint": "sha256:finance-analysts",
                    "mapping_rule_id": "rule-finance-analysts-v1",
                    "review_state": "current",
                },
            },
        )

    def test_stale_mapping_fails_closed_with_explicit_state(self) -> None:
        payload = _valid_bridge_payload()
        payload["governance_bindings"] = [
            {
                "binding_type": "group",
                "value": "finance-analysts",
                "source_claim": "groups",
                "mapping_state": "stale",
                "mapping_evidence": {
                    "claim_issuer": "https://idp.example.test",
                    "claim_value_fingerprint": "sha256:finance-analysts",
                    "mapping_rule_id": "rule-finance-analysts-v1",
                    "review_state": "expired",
                },
            }
        ]

        with self.assertRaisesRegex(ValidationError, "stale"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_ambiguous_mapping_fails_closed_with_explicit_state(self) -> None:
        payload = _valid_bridge_payload()
        payload["governance_bindings"] = [
            {
                "binding_type": "group",
                "value": "finance-analysts",
                "source_claim": "groups",
                "mapping_state": "ambiguous",
                "mapping_evidence": {
                    "claim_issuer": "https://idp.example.test",
                    "claim_value_fingerprint": "sha256:finance-analysts",
                    "mapping_rule_id": "rule-conflict-v1",
                    "review_state": "multiple_matches",
                },
            }
        ]

        with self.assertRaisesRegex(ValidationError, "ambiguous"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_unsupported_mapping_fails_closed_with_explicit_state(self) -> None:
        payload = _valid_bridge_payload()
        payload["governance_bindings"] = [
            {
                "binding_type": "group",
                "value": "finance-analysts",
                "source_claim": "groups",
                "mapping_state": "unsupported",
                "mapping_evidence": {
                    "claim_issuer": "https://idp.example.test",
                    "claim_value_fingerprint": "sha256:finance-analysts",
                    "mapping_rule_id": "rule-unsupported-v1",
                    "review_state": "unsupported_claim",
                },
            }
        ]

        with self.assertRaisesRegex(ValidationError, "unsupported"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_missing_mapping_evidence_fails_closed(self) -> None:
        payload = _valid_bridge_payload()
        payload["governance_bindings"] = [
            {
                "binding_type": "group",
                "value": "finance-analysts",
                "source_claim": "groups",
                "mapping_state": "missing",
            }
        ]

        with self.assertRaisesRegex(ValidationError, "missing"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_mapping_evidence_rejects_workstation_local_paths(self) -> None:
        payload = _valid_bridge_payload()
        local_path = "/" + "Users" + "/" + "alice" + "/SafeQuery/mapping.json"
        payload["governance_bindings"] = [
            {
                "binding_type": "group",
                "value": "finance-analysts",
                "source_claim": "groups",
                "mapping_state": "valid",
                "mapping_evidence": {
                    "claim_issuer": "https://idp.example.test",
                    "claim_value_fingerprint": "sha256:finance-analysts",
                    "mapping_rule_id": local_path,
                    "review_state": "current",
                },
            }
        ]

        with self.assertRaisesRegex(ValidationError, "workstation-local paths"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_mapping_evidence_rejects_secret_markers(self) -> None:
        payload = _valid_bridge_payload()
        payload["governance_bindings"] = [
            {
                "binding_type": "group",
                "value": "finance-analysts",
                "source_claim": "groups",
                "mapping_state": "valid",
                "mapping_evidence": {
                    "claim_issuer": "https://idp.example.test",
                    "claim_value_fingerprint": "token=raw-idp-token",
                    "mapping_rule_id": "rule-finance-analysts-v1",
                    "review_state": "current",
                },
            }
        ]

        with self.assertRaisesRegex(ValidationError, "secrets or credentials"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_missing_subject_fails_closed(self) -> None:
        payload = _valid_bridge_payload()
        payload.pop("subject")

        with self.assertRaisesRegex(ValidationError, "subject"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_missing_actor_fails_closed(self) -> None:
        payload = _valid_bridge_payload()
        payload.pop("actor")

        with self.assertRaisesRegex(ValidationError, "actor"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_actor_and_subject_must_share_authoritative_identity(self) -> None:
        payload = _valid_bridge_payload()
        payload["actor"] = {
            "actor_id": "user:delegated-admin@example.com",
            "actor_type": "human_user",
            "issuer": "https://idp.example.test",
        }

        with self.assertRaisesRegex(ValidationError, "actor.*subject"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_actor_and_subject_must_share_authoritative_issuer(self) -> None:
        payload = _valid_bridge_payload()
        payload["actor"] = {
            "actor_id": "user:alice@example.com",
            "actor_type": "human_user",
            "issuer": "https://idp-a.example.test",
        }
        payload["subject"] = {
            "subject_id": "user:alice@example.com",
            "subject_type": "human_user",
            "idp_subject": "00u-enterprise-alice",
            "issuer": "https://idp-b.example.test",
        }

        with self.assertRaisesRegex(ValidationError, "actor issuer.*subject issuer"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_missing_governance_bindings_fail_closed(self) -> None:
        payload = _valid_bridge_payload()
        payload["governance_bindings"] = []

        with self.assertRaisesRegex(ValidationError, "governance_bindings"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_duplicate_normalized_bindings_fail_closed(self) -> None:
        payload = _valid_bridge_payload()
        payload["governance_bindings"] = [
            {
                "binding_type": "group",
                "value": "finance-analysts",
                "source_claim": "groups",
                "mapping_state": "valid",
                "mapping_evidence": _mapping_evidence("rule-finance-analysts-v1"),
            },
            {
                "binding_type": "group",
                "value": " finance-analysts ",
                "source_claim": "groups",
                "mapping_state": "valid",
                "mapping_evidence": _mapping_evidence("rule-finance-analysts-copy-v1"),
            },
        ]

        with self.assertRaisesRegex(ValidationError, "Duplicate governance binding"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_unsupported_claim_shapes_fail_closed(self) -> None:
        payload = _valid_bridge_payload()
        payload["governance_bindings"] = "group:finance-analysts"

        with self.assertRaisesRegex(ValidationError, "governance_bindings"):
            normalize_enterprise_auth_bridge_input(payload)

    def test_raw_tokens_and_secrets_are_not_exposed_in_serialized_context(self) -> None:
        serialized = normalize_enterprise_auth_bridge_input(
            _valid_bridge_payload()
        ).model_dump()

        self.assertNotIn("raw_token", str(serialized))
        self.assertNotIn("client_secret", str(serialized))
        self.assertNotIn("<bridge-token-redacted>", str(serialized))
        self.assertNotIn("<client-secret-redacted>", str(serialized))


if __name__ == "__main__":
    unittest.main()
