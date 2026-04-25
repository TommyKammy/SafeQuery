from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.features.auth.bridge import normalize_enterprise_auth_bridge_input


def _valid_bridge_payload() -> dict[str, object]:
    return {
        "bridge_source": "saml-oidc-bridge",
        "subject": {
            "subject_id": " user:alice@example.com ",
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
            },
            {
                "binding_type": "role",
                "value": " sql-reviewer ",
                "source_claim": "roles",
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
        self.assertEqual(context.session.session_id, "session-123")
        self.assertEqual(
            context.authenticated_subject.normalized_governance_bindings(),
            frozenset({"group:finance-analysts", "role:sql-reviewer"}),
        )
        self.assertEqual(
            context.audit_metadata.model_dump(),
            {
                "bridge_source": "saml-oidc-bridge",
                "subject_id": "user:alice@example.com",
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
                    },
                    {
                        "binding": "role:sql-reviewer",
                        "binding_type": "role",
                        "source_claim": "roles",
                        "bridge_source": "saml-oidc-bridge",
                    },
                ],
            },
        )

    def test_missing_subject_fails_closed(self) -> None:
        payload = _valid_bridge_payload()
        payload.pop("subject")

        with self.assertRaisesRegex(ValidationError, "subject"):
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
            },
            {
                "binding_type": "group",
                "value": " finance-analysts ",
                "source_claim": "groups",
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
