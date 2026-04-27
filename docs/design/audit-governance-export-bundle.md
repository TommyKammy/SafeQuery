# Dedicated Governance Review Export Contract

SafeQuery governance review evidence must be available as a dedicated export
contract separate from the support bundle. The support bundle remains a bounded
operator diagnostic artifact; it must not become the reviewer-scoped evidence
artifact for source governance, audit reconstruction, release posture, or
execution-bound review.

The dedicated export is generated from persisted SafeQuery control-plane
records and can be produced from local fixture data without live source,
adapter, search, analyst, MLflow, or LLM services. It is review evidence only:
it does not authorize execution, approve candidates, refresh stale approvals,
or substitute for entitlement checks, SQL Guard, source activation posture, or
execution policy revalidation.

## Contract Shape

The export shape should be a JSON artifact or a future read-only endpoint with
the same payload contract:

```json
{
  "contract": "safequery.governance_review_export.v1",
  "generatedAt": "<iso-8601-timestamp>",
  "generatedBy": {
    "authority": "safequery_control_plane",
    "reviewerScope": "reviewer-only",
    "actorId": "<redacted-reviewer-id>"
  },
  "filters": {
    "sourceIds": ["<source-id>"],
    "sourceFamilies": ["postgresql", "mssql"],
    "timeWindow": {
      "from": "<iso-8601-timestamp>",
      "to": "<iso-8601-timestamp>"
    },
    "requestIds": ["<request-id>"],
    "candidateIds": ["<candidate-id>"]
  },
  "authority": {
    "recordStore": "safequery_control_plane",
    "snapshotId": "<committed-snapshot-id>",
    "snapshotConsistency": "single_committed_snapshot"
  },
  "evidence": []
}
```

The initial CLI artifact can use repo-local fixture or backend records. A future
endpoint may expose the same contract at a reviewer-only route such as
`GET /governance/review-export`, but that endpoint must be a separate
implementation follow-up and must not reuse unrestricted support-bundle
posture as authorization.

## Filters and Scope

The export request must define an explicit source filter, time window, and
reviewer scope before evidence is assembled:

- `sourceIds` or `sourceFamilies` restrict the export to approved source
  records that the reviewer is allowed to inspect.
- `timeWindow.from` and `timeWindow.to` bound the lifecycle, audit, release-gate,
  and governance records included in the artifact.
- Optional `requestIds` and `candidateIds` narrow the export to direct
  authoritative records only. They must not pull sibling requests, same-parent
  candidates, or adjacent evidence by naming convention.
- Empty, malformed, unauthorized, or mixed-scope filters fail closed instead of
  producing a broad export.

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

Each evidence item is scoped to one request and, when present, one candidate.
The export carries source identity, source family and flavor, dataset contract
version, schema snapshot version, lifecycle event order, actor metadata,
candidate guard state, review approval metadata, release-gate status, and
execution result metadata. Evidence must be read from one committed control-plane
snapshot or rejected as mixed-snapshot state.

## Redaction and Forbidden Values

The dedicated export uses explicit redaction. It may include durable record ids,
timestamps, source ids, source family and flavor, dataset contract versions,
schema snapshot versions, lifecycle state, deny codes, approval metadata,
release-gate status, audit completeness status, and bounded result metadata.

It must include no raw credentials, no connection strings, no database URLs, no
passwords, no tokens, no cookies, no CSRF secrets, no private keys, no raw
identity payloads, no raw SQL, no raw result rows, no source connection
references, and no workstation-local absolute paths.

Redacted fields should be omitted or replaced with stable redaction markers such
as `<redacted>`. A missing field means unavailable or intentionally redacted; it
is not proof that the omitted action was safe.

## Authority Requirements

The export is reviewer-only. The caller must already have a trusted SafeQuery
reviewer authorization context bound to the requested source and time filters.
Forwarded headers, unsigned identity fields, placeholder credentials, sample
tokens, or TODO values are not valid reviewer authority.

When provenance, auth context, source binding, snapshot consistency, or filter
authority is missing or only partially trusted, generation must fail closed. The
exporter must not infer tenant, repository, account, issue, source, or candidate
linkage from path shape, comments, display names, or nearby metadata.

## Support Bundle Relationship

The support bundle may keep a compact `governanceReview` summary for bounded
operator triage, but that summary is not the dedicated governance review export.
Support-bundle posture does not grant reviewer access, does not broaden export
filters, and does not replace the dedicated redaction and authority checks
above.

Use the support bundle for operational diagnosis. Use the dedicated governance
review export when a reviewer needs source- and time-bounded governance evidence
that can be evaluated without raw secrets, local paths, unrestricted support
context, or execution authority.

## Export Limitations

The export summarizes a committed database snapshot at generation time. It does
not prove that external services were reachable later, that a subordinate
adapter's own logs are complete, or that an external system retained matching
evidence.

Implementation of a served endpoint, download flow, or signed artifact is
explicitly deferred until a separate implementation follow-up defines the exact
authorization middleware, snapshot read boundary, redaction tests, and reviewer
UX. Reopen this design if implementation work cannot preserve reviewer-only
scope, source/time filtering, redaction, and fail-closed behavior without
changing the contract.

## Local Verification

Focused verification should use local persisted records or fixture-backed tests:

```bash
bash tests/smoke/test-pilot-safety-checklist.sh

cd backend
python3 -m pytest tests/test_support_bundle.py
```

Generated exports should be inspected for:

- lifecycle completeness across request, candidate, review, and execution
  records
- clear authority labels on control-plane and subordinate evidence
- reviewer-only scope and explicit source filter and time window values
- absence of raw SQL, result rows, credentials, tokens, connection strings, raw
  identity payloads, connection references, and workstation-local absolute paths
