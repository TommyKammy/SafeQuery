# Audit Governance Export Bundle

The support bundle includes a `governanceReview` section for read-only lifecycle
review. It is generated from persisted SafeQuery control-plane records and can
be produced from local fixture data without live source, adapter, search,
analyst, MLflow, or LLM services.

## Reviewer Expectations

Reviewers should treat `governanceReview.authority` and each evidence
`authority` value as the first trust boundary signal:

- `safequery_control_plane` records are authoritative SafeQuery records persisted
  by the backend control plane.
- `subordinate_adapter` metadata is supporting generation context. It can help
  identify which adapter, model, prompt version, or run produced a candidate, but
  it does not authorize execution.
- UI, external connector, LLM, search, analyst, and MLflow evidence must remain
  subordinate unless a future control-plane record explicitly promotes a field
  into an authoritative SafeQuery record.

Each evidence item is scoped to one request and, when present, one candidate. The
bundle carries source identity, source family and flavor, dataset contract
version, schema snapshot version, lifecycle event order, actor metadata,
candidate guard state, review approval metadata, and execution result metadata.

## Export Limitations

The bundle is review evidence only. It does not approve, re-approve, or authorize
execution. Reviewers must not use it as a bypass for candidate approval,
entitlement checks, SQL Guard, source activation posture, or execution policy
revalidation.

The export intentionally excludes raw SQL, raw result rows, connection strings,
raw credentials, tokens, raw identity payloads, source connection references,
and workstation-local paths. A missing field should be interpreted as
unavailable or intentionally redacted, not as proof that an action was safe.

The bundle summarizes a committed database snapshot at generation time. It does
not prove that external services were reachable later, that a subordinate
adapter's own logs are complete, or that an external system retained matching
evidence.

## Local Verification

Focused verification should use local persisted records or fixture-backed tests:

```bash
cd backend
python3 -m pytest tests/test_support_bundle.py
```

Generated exports should be inspected for:

- lifecycle completeness across request, candidate, review, and execution
  records
- clear authority labels on control-plane and subordinate evidence
- absence of raw SQL, result rows, credentials, tokens, raw identity payloads,
  connection references, and workstation-local paths
