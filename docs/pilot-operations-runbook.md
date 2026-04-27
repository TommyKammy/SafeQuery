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

## Command-backed classification signals

Use command-backed evidence when a state depends on local first-run health or
workflow availability:

| Assumption | Command-backed signal | Manual/operator judgment |
| --- | --- | --- |
| First-run control-plane readiness | `python -m app.cli.first_run_doctor` reports `status: pass` and includes `database`, `migrations`, `source_registry`, `dataset_contract`, `schema_snapshot`, `entitlement_seed`, `execution_connector`, `backend`, and `frontend` checks. | Decide whether the current pilot window is allowed to rely on local first-run evidence or needs production deployment evidence. |
| Live backend health | `curl http://localhost:8000/health` reports `status: ok` with healthy database and operator health components for the local stack. | Decide whether degraded optional components affect the specific pilot path. |
| Source selector workflow availability | `curl http://localhost:8000/operator/workflow` returns a non-empty active source selector from backend records. | Decide whether the selected source is in the approved pilot scope for the current operator group. |
| Pilot UI workflow safety smoke | `bash tests/smoke/test-pilot-safety-ui-workflow.sh` passes source selection, source-bound preview, execution posture, result, and audit surface checks without Docker. | Use this first when an operator-facing workflow surface regressed. |
| Pilot API preview safety smoke | `bash tests/smoke/test-pilot-safety-api-preview.sh` passes preview persistence, source entitlement denial, and guard audit checks without Docker. | Use this first when preview or guard behavior regressed. |
| Pilot API execute safety smoke | `bash tests/smoke/test-pilot-safety-api-execute.sh` passes candidate-only execute, result inspection, cancellation, and audit history checks without Docker. | Use this first when execute, result, or audit-history behavior regressed. |
| Pilot aggregate safety smoke | `bash tests/smoke/test-pilot-safety-ui-api-workflow.sh` passes the local unit-contract smoke path without Docker. | Decide whether compose-backed or real-source smokes are also required for the affected pilot window. |
| Compose-backed first-run path | `bash tests/smoke/test-compose-operator-workflow-source-selector.sh` passes when Docker and `docker-compose` are available. | Decide whether unavailable host dependencies make this a deferred manual check instead of a failed product signal. |

If a row has no current command-backed signal, record it as Manual/operator
judgment in the pilot note. Do not infer normal, degraded, maintenance,
incident, or recovery posture from UI text alone.

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

## Pilot Migration Backup and Rollback Runbook

Use this runbook before changing the SafeQuery application database schema or
rolling out runtime changes that depend on a new migration head. It covers
application database migrations only. Business source connectivity checks are a
separate source-readiness concern: they may prove that an explicitly registered
business PostgreSQL or MSSQL source is reachable, but they do not replace
application migration evidence and must not reuse application database
credentials.
Treat business source connectivity checks as independent readiness evidence,
not as proof that application database migrations are safe or current.

Run these steps with the environment-value contract in
[pilot-deployment-profile.md](./pilot-deployment-profile.md) and capture only
bounded diagnostic artifacts described in
[Secret-Safe Support Bundle](#secret-safe-support-bundle). Keep evidence free
of database URLs, passwords, tokens, raw result rows, raw SQL, and
workstation-local absolute paths.

### Migration preflight

Before applying a migration, put the affected pilot path in Maintenance and
record before-migration evidence:

- pilot window, operator, affected environment label, and affected source ids
  if any source records are expected to be read after migration
- current commit or release identifier and expected Alembic head
- current migration posture from the application database:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend alembic current
```

- first-run doctor output after environment setup and before the migration:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend python -m app.cli.first_run_doctor
```

- support-bundle or equivalent bounded diagnostic artifact when reviewers need
  a shareable snapshot of migration posture and health summaries

Stop before applying the migration if the application database is unreachable,
the current head is unknown, the expected head is not documented, required env
values are missing or placeholder-like, the backup plan is absent, or the pilot
cannot be paused for the affected surface.

### Backup expectations

Take a backup of the application database before any pilot migration that
changes durable records or runtime expectations. The backup artifact identifier
must be recorded in the maintenance note along with the command family used,
the environment label, the application database name or bounded database id,
the timestamp, and the operator who verified the artifact exists.

The runbook does not prescribe a universal backup command because the pilot
database host, permissions, encryption, and retention policy are deployment
specific. Use the deployment-approved backup mechanism for the application
database. Do not place raw backup paths, credentials, connection URLs, or
storage tokens in shared docs, issues, support bundles, or screenshots.

Before continuing, an operator must be able to answer:

- where the backup is stored inside the approved backup boundary
- which application database and migration head it represents
- how the artifact will be integrity-checked before any restore attempt
- who is authorized to approve restore or destructive rollback steps

### Apply and verify

Apply migrations through the repo-owned backend context so Alembic uses the same
application settings as the pilot stack:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend alembic upgrade head
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend alembic current
```

After the migration, record after-migration evidence from authoritative
surfaces:

- `alembic current` reports the expected head
- `python -m app.cli.first_run_doctor` reports the expected migration posture
  and still distinguishes migrations from source registry, entitlement,
  connector, backend, and frontend checks
- the relevant smoke or release-gate command for the changed surface passed
- support bundle migration posture is current when a bounded diagnostic artifact
  is needed for review
- operator workflow state is refreshed from backend records, not from stale UI
  summaries or prior support bundles

If a business source connectivity check fails after a successful application
migration, keep the source path degraded or blocked and troubleshoot source
registry, connector profile, secret indirection, entitlement, and network
readiness separately. Do not roll back an application migration solely because
an unrelated business source probe failed.

### Rollback decision guidance

Rollback is a decision point, not an automatic command.
Do not run destructive rollback or restore commands without explicit operator
confirmation.
Require a verified backup artifact identifier and an owner for the affected
pilot window before any rollback or restore attempt.

Prefer the least destructive recovery path that keeps authority boundaries
intact:

- if the migration failed before durable writes, keep pilot traffic paused,
  preserve logs and command output, and rerun only after the cause is clear
- if the migration applied but verification failed, keep the system in
  Recovery, block affected pilot use, and compare migration posture,
  first-run doctor output, support-bundle migration posture, and audit evidence
  from one current snapshot
- if a forward fix is safer than restore, document the fix, rerun the same
  verification commands, and keep old candidates, runs, exports, and UI
  summaries from being reused as current evidence
- if restore is required, escalate for the deployment-approved restore
  procedure and verify that no orphan records, partial durable writes,
  half-restored state, or mixed-snapshot evidence remains

Never infer rollback safety from service names, path shape, nearby comments,
client-provided headers, or UI status text. If provenance, scope, backup
integrity, auth context, or source binding is missing, keep the rollback path
blocked until the prerequisite is real.

### Post-incident notes

After a failed migration, unsafe rollout, restore, or rollback decision, record:

- the before-migration evidence and after-migration evidence that were captured
- exact command names, exit status, and bounded output summaries
- migration head before and after the attempt
- backup artifact identifier and whether integrity verification was completed
- affected source ids, request ids, candidate ids, run ids, and audit ids
- whether application database migrations or business source connectivity
  checks caused the failure
- whether any partial durable write, orphan record, half-restored state, stale
  candidate, missing audit event, or mixed-snapshot read set survived
- recovery verification commands and the explicit operator decision to resume,
  keep degraded, escalate, or stop the pilot path

Do not attach secrets, raw SQL, raw rows, database URLs, connection strings,
tokens, cookies, private keys, source connection references, or local
user-profile paths to the post-incident note.

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

## Secret-Safe Support Bundle

Use the support bundle when a pilot reviewer needs bounded diagnostic context
for normal, degraded, maintenance, or recovery triage and the operator does not
need to share raw logs, direct database credentials, query result rows, or local
machine paths.

Generate the bundle from the backend environment that is already configured for
SafeQuery:

```bash
cd backend
python -m app.cli.support_bundle > support-bundle.json
```

If the backend API is already running, operators can capture the same bounded
artifact from the served endpoint:

```bash
curl http://localhost:8000/support/bundle > support-bundle.json
```

The bundle is intended to include application version, environment, source
posture, migration posture, active source ids, health components, recent
workflow state summaries, lifecycle metrics, and audit completeness counts. It
is intentionally not an export of operator prompts, raw SQL, raw result rows,
connection strings, tokens, credentials, source connection references, or
workstation-local absolute paths.

Before sharing the artifact, inspect it as text and stop if it contains a
credential, token, connection URL, connection string, raw row payload, private
SQL text, or local user-profile path:

```bash
python -m json.tool support-bundle.json >/dev/null
```

Stop and escalate instead of sharing a bundle when the issue concerns suspected
secret exposure, untrusted auth context, source-binding ambiguity, raw SQL
execute exposure, missing audit coverage, mixed-snapshot state, or partial
restore/export behavior. In those cases, preserve the affected request ids,
candidate ids, audit ids, run ids, source ids, and command outputs, then follow
the Incident or Recovery sections above.
