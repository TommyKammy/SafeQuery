# Pilot Operations Runbook and Incident State Taxonomy

## Purpose

This runbook gives pilot operators a shared vocabulary for SafeQuery posture
during limited pilot use. It defines normal, degraded, maintenance, incident,
and recovery states across the workflow surfaces an operator can inspect:
preview, generation, guard, execute, audit, source connectivity, and operator UI.

Use this runbook with
[pilot-safety-verification-checklist.md](./pilot-safety-verification-checklist.md)
and [local-development.md](./local-development.md). The checklist proves whether
the pilot gate is ready; this runbook tells operators how to classify and react
to the state they see during pilot operations.

## Authority Boundary

SafeQuery control-plane records are authoritative. Resolve workflow truth from
backend-owned records for source registry posture, selected source, entitlement,
request, candidate, guard, approval, execution run, audit event, release gate,
and first-run doctor outcomes.

UI, LLM, adapter, MLflow, Search, Analyst, and external evidence are subordinate
surfaces. They may help diagnose a state, but they do not override the
application control plane. When subordinate evidence disagrees with the
control-plane record, keep the workflow blocked or degraded and repair the
derived surface.

Do not infer source, tenant, repository, environment, user, candidate, or run
linkage from naming conventions, service names, comments, hostnames, forwarded
headers, file paths, or nearby metadata. Require the explicit authoritative
record. Missing, malformed, stale, placeholder, or mixed-snapshot prerequisite
signals are blocked states, not soft passes.

## Operator Classification Flow

1. Start from the current control-plane record: first-run doctor, workflow
   payload, request, candidate, guard, execution run, audit event, or release
   gate record.
2. Confirm the record is source-scoped and snapshot-consistent. Do not stitch
   together old doctor output, new UI state, and unrelated audit rows.
3. Classify the posture using the most severe active state below. Incident
   outranks maintenance, recovery, degraded, and normal.
4. Take only the safe first checks listed for that state.
5. Stop or escalate when an execute, guard, audit, source-binding, auth, or
   mixed-state boundary is unclear.

## Incident State Taxonomy

| State | Operational meaning | Pilot posture |
| --- | --- | --- |
| Normal | All required control-plane records agree, and pilot workflow surfaces are available. | Pilot use may continue within approved scope. |
| Degraded | A subordinate or non-execute surface is impaired, while authoritative controls still block unsafe paths. | Continue only the unaffected pilot path; record the degraded surface. |
| Maintenance | An operator intentionally changes or verifies the stack, data, config, migrations, connectors, or release gate. | Pause affected pilot traffic until checks finish. |
| Incident | A safety, authority, audit, execute, source-binding, auth, or data-integrity boundary is missing, contradicted, or suspected compromised. | Stop affected pilot use and escalate. |
| Recovery | Incident or maintenance work is complete enough to verify, but pilot use has not been re-authorized by control-plane evidence. | Reopen only after recovery checks pass from authoritative records. |

## Surface Expectations

| Surface | Normal | Degraded | Maintenance | Incident | Recovery |
| --- | --- | --- | --- | --- | --- |
| preview | Candidate preview is read-only, source-bound, and tied to current request and candidate records. | Preview is unavailable or slow, but no execute path is exposed and stale candidates remain blocked. | Preview checks may be intentionally paused while migrations, seed data, or guard profiles are verified. | Preview shows editable raw SQL, wrong source, stale candidate, missing entitlement, or mixed record context. | Preview works only after a fresh candidate is generated or revalidated against current source, auth, and guard records. |
| generation | Adapter request uses one authoritative source, schema snapshot, dataset contract, and dialect profile. | Generation is unavailable, times out, or lacks optional enrichment while preview and execute stay blocked. | Generation adapters or profiles are being configured or evaluated outside pilot traffic. | Generation uses guessed source context, placeholder credentials, cross-source schema, untrusted identity, or unsigned output as authority. | Regenerate against current authoritative source context; do not reuse incident-era candidates. |
| guard | Guard policy, deny code, dialect profile, and source identity are explicit. | Guard is stricter than expected or blocks extra requests; pilot continues only for paths with current pass evidence. | Guard catalog, deny corpus, or dialect profile is under planned verification. | Guard is bypassed, missing, stale, accepts unsupported syntax, or cannot prove the source-bound policy version. | Rerun guard checks and deny corpus evidence before preview or execute is treated as pilot-ready. |
| execute | Execute accepts only an approved candidate identifier and enforces ownership, source, TTL, runtime controls, and connector selection. | Execute is disabled or limited by rate limit, kill switch, row cap, or connector health while unsafe dispatch remains blocked. | Execute stays paused for connector, secret, migration, release-gate, or runtime-control work. | Raw SQL execution is exposed, connector dispatch occurs without valid candidate approval, or source/owner/runtime checks are unclear. | Execute remains blocked until fresh candidate, approval, source, connector, runtime, and audit evidence agree. |
| audit | Audit events preserve request, source, candidate, run, guard, auth, entitlement, and correlation anchors. | Audit display or export is delayed, but the durable audit record remains complete. | Audit schema, replay, export, or release-gate reconstruction is intentionally under review. | Required audit fields are missing, contradictory, redacted incorrectly, mixed across snapshots, or absent after a denied/failed path. | Reconstruct from durable audit records and prove denied, failed, and recovered paths left no orphan durable state. |
| source connectivity | Active sources match backend-owned registry, connector profile, secret indirection, and readiness checks. | One source is unavailable; other sources may continue only if explicitly independent and release-gate evidence is current. | Source registry, connector profile, or secret wiring is being changed or rotated. | Source identity is inferred from service names, reused application database credentials, unknown secrets, or client-supplied hints. | Reconfirm registry, entitlement, connector, secret readiness, and first-run doctor evidence before resuming that source. |
| operator UI | UI reflects backend workflow state and keeps request, source, candidate, guard, run, and audit anchors visible. | UI summary, badge, or optional panel is stale while backend controls remain authoritative and visible enough to operate safely. | UI or docs are under planned pilot verification. | UI lets operators act on stale, guessed, hidden, or contradicted control-plane state. | UI can be used again only after it is refreshed from authoritative records and no stale actions remain available. |

## Normal

Operational meaning:

- The first-run doctor, workflow payload, source registry, entitlement, request,
  candidate, guard, execute, audit, and release-gate evidence agree.
- Optional search, analyst, and MLflow surfaces may be present, but they are
  evidence helpers only.

operator-facing symptoms:

- The operator shell loads current source options from `/operator/workflow`.
- Preview is read-only and shows current request, source, candidate, and guard
  anchors.
- Execute is available only through an approved candidate identifier.
- Audit and history surfaces show matching source, candidate, run, and denial
  anchors.

safe first checks:

- Run the focused pilot checks from
  [pilot-safety-verification-checklist.md](./pilot-safety-verification-checklist.md)
  when entering or re-entering a pilot window.
- Confirm `curl http://localhost:8000/health` and
  `curl http://localhost:8000/operator/workflow` report expected health and
  source selector state for local pilot evaluation.
- Confirm the current release gate and required smoke evidence are from the
  same pilot window.

stop or escalate:

- Stop if any subordinate surface contradicts a control-plane record.
- Escalate if normal status depends on guessed source, stale candidate,
  placeholder credential, untrusted identity, or missing audit evidence.

## Degraded

Operational meaning:

- A non-authoritative surface, optional extension, or limited connector path is
  impaired, while the control plane still blocks unsafe preview, generation,
  guard, execute, and audit paths.

operator-facing symptoms:

- UI badges, summaries, optional search, analyst, or MLflow panels lag behind
  the backend record.
- Generation, preview, or execute is temporarily unavailable for one source, but
  blocked paths remain visibly blocked.
- The first-run doctor reports a degraded or failed dependency that does not
  create execute authority.

safe first checks:

- Compare the UI state with the backend workflow payload and durable audit
  records.
- Check whether the affected source has an independent registry, entitlement,
  connector, guard, and release-gate path before allowing another source to
  continue.
- Record the degraded surface and the authoritative record used to classify it.

stop or escalate:

- Stop affected pilot use when degradation touches guard, execute, audit,
  source binding, auth, entitlement, or release-gate reconstruction.
- Escalate if operators cannot tell which control-plane record is current.

## Maintenance

Operational meaning:

- An operator intentionally changes, verifies, or pauses part of the pilot
  stack: migrations, seed data, registry records, connector profiles, guard
  profiles, release-gate evidence, docs, or UI rollout.

operator-facing symptoms:

- Pilot traffic is paused or narrowed for the affected source or surface.
- Maintenance notes identify the planned command, expected state change, and
  rollback or stop condition.
- First-run doctor, release gate, or smoke commands may be intentionally rerun.

safe first checks:

- Announce the affected surfaces before changing them.
- Use repo-relative commands from the docs and placeholders such as
  `<supervisor-config-path>` for supervisor-specific notes.
- Verify the intended state through authoritative records after the change,
  not through UI summary text alone.

stop or escalate:

- Stop if a migration, seed, restore, export, or connector update leaves partial
  durable state, orphan records, or mixed-snapshot evidence.
- Escalate if rollback requires secrets, permissions, production data access, or
  a decision outside the documented pilot scope.

## Incident

Operational meaning:

- A trusted boundary is missing, contradicted, bypassed, or suspected
  compromised. Incidents include unclear source binding, raw SQL execute
  exposure, missing audit coverage, untrusted auth context, placeholder
  credentials treated as valid, mixed-snapshot state, partial restore, or
  release-gate evidence that cannot be reconstructed.

operator-facing symptoms:

- Preview, execute, audit, or UI state disagrees with the authoritative
  candidate, source, guard, or run record.
- Execute dispatch appears possible without a current approved candidate.
- Denied or failed paths leave partial durable state or no audit record.
- Source, tenant, user, repo, issue, or environment linkage is inferred from
  names, headers, comments, or path shape instead of explicit records.

safe first checks:

- Stop the affected pilot path before gathering more evidence.
- Preserve current logs, doctor output, release-gate output, request ids,
  candidate ids, run ids, audit ids, and source ids.
- Identify the earliest authoritative record that became missing, stale,
  mixed, or contradicted.

stop or escalate:

- Escalate immediately for any execute-boundary, auth, secret, audit,
  source-binding, restore, export, or data-integrity uncertainty.
- Do not regenerate, approve, execute, delete, restore, or reclassify records to
  make the incident look normal until the authoritative cause is understood.

## Recovery

Operational meaning:

- The immediate incident or maintenance action is complete, but pilot use is
  still blocked until current control-plane evidence proves the affected
  workflow is safe.

operator-facing symptoms:

- The UI may appear healthy before current doctor, release-gate, smoke, audit,
  and workflow records are all refreshed.
- Old candidates, runs, previews, exports, or audit summaries may still exist
  from the incident window.
- Operators need a fresh sign-off point before resuming affected pilot traffic.

safe first checks:

- Rerun the focused pilot checks listed in the checklist for the affected
  surfaces.
- Verify no orphan record, partial durable write, half-restored state, stale
  candidate, or unaudited denial survived the failed path.
- Create fresh candidate, guard, approval, execute, and audit evidence where the
  incident touched those records; do not reuse incident-era candidate evidence.

stop or escalate:

- Stop recovery if any required record cannot be tied to the current source,
  auth context, candidate, run, audit, and release-gate window.
- Escalate if recovery depends on manual database edits, secret rotation,
  external vendor action, or unreviewed policy changes.

## Minimum Evidence to Record

For degraded, maintenance, incident, and recovery states, record:

- classified state and affected source or surface
- current authoritative record ids or command outputs
- operator-facing symptoms observed
- safe first checks performed
- stop or escalate decision and owner
- recovery verification commands and results, when recovery starts

Keep durable notes path-hygienic. Use repo-relative command forms and explicit
placeholders rather than raw workstation-local absolute paths.
