# Threat Model

## Purpose

This document summarizes the initial SafeQuery threat model for the pilot-safe PoC.

## Protected Assets

- approved business data exposed through the allow-listed dataset
- approved retrieval corpus assets and citation integrity
- SQL Server execution credentials
- application audit records
- MLflow engineering traces and evaluation records
- authorization and session integrity
- candidate approval and execution integrity

## Assumed Threats

- a legitimate authenticated user attempting out-of-scope data access
- prompt-driven generation of unsafe or unauthorized SQL
- client-side tampering with execution requests
- accidental data overexposure through schema drift or bad allow-lists
- stale or poisoned retrieval assets influencing analyst answers
- oversharing sensitive inputs or outputs into MLflow traces
- operational misuse such as unbounded queries or repeated execution attempts

## Actor-Focused Abuse Cases

### Legitimate but curious user

- likely goal: access out-of-scope data through prompt phrasing or repeated query attempts
- protected assets: allow-listed dataset boundary and result data
- baseline controls: dataset governance, SQL Guard, candidate ownership, rate limits, audit trail

### Compromised browser or frontend path

- likely goal: replay or tamper with execution requests
- protected assets: candidate integrity, session integrity, SQL Server execution path
- baseline controls: `query_candidate_id` ownership checks, CSRF controls, opaque IDs, replay limits, no raw-SQL execute endpoint

### Malicious or broken adapter output

- likely goal: produce unsafe or out-of-policy SQL
- protected assets: SQL Server scope, application trust boundary
- baseline controls: adapter isolation, parser-oriented SQL Guard, deny corpus, application-owned execution control

### Operational misconfiguration

- likely goal: accidental rather than malicious, such as stale allow-lists or bad retention posture
- protected assets: data exposure scope, audit store, pilot safety
- baseline controls: governance approvals, schema-drift review, invalidation rules, sensitive-store posture

### Retrieval asset drift or poisoning

- likely goal: inject stale, misleading, or over-broad semantic assets into search and analyst flows
- protected assets: citation integrity, analyst output quality, governed knowledge surface
- baseline controls: asset-owner approval, security review, retrieval corpus versioning, invalidation workflow, citation display

### MLflow trace leakage

- likely goal: create a shadow store of sensitive prompts, SQL, or result fragments through engineering tracing
- protected assets: sensitive business inputs, result confidentiality, governance boundary clarity
- baseline controls: MLflow export contract, redaction rules, short retention, least-privilege access, PostgreSQL as authoritative audit store

## Baseline Controls

- application-owned authentication consumption and authorization
- adapter isolation from production SQL Server credentials
- application-owned SQL Guard
- candidate-based approval and execution integrity
- retrieval asset governance and authorization
- citation labeling and evidence separation
- MLflow export restrictions and retention controls
- result limits, timeout, cancellation, and kill switch controls
- application-owned auditing in PostgreSQL

## Likelihood and Impact Lens

- curious-user data overreach: medium likelihood, high impact
- frontend-path replay or tampering: low-to-medium likelihood, high impact
- unsafe adapter output: medium likelihood, high impact
- operational misconfiguration: medium likelihood, medium-to-high impact

## Detective Controls

- audit review for denied and successful execution events
- alerts on repeated rate-limit or execution-denied spikes
- monitoring for candidate invalidation and replay-denial events
- schema-drift review before allow-list updates take effect
- retrieval corpus change review and citation anomaly review
- monitoring for unexpected sensitive-field exports into MLflow

## Residual Risks

- generation quality may still be poor even when safety controls hold
- allow-list mistakes can still expose the wrong dataset if governance is weak
- denial rules may need refinement as new T-SQL edge cases are discovered
- analyst outputs can still be misleading if retrieval quality is weak despite correct authorization
- MLflow handling still depends on disciplined redaction and access review
- pilot operators still need monitoring and review discipline

## Pilot Readiness View

The pilot should not claim general enterprise safety only from architectural intent. It should demonstrate:

- bounded dataset exposure
- bounded execution behavior
- reproducible audit trails
- tested deny behavior for unsafe SQL

## Follow-Up Work

The next iterations should deepen:

- abuse-case enumeration by actor type
- schema drift detection workflow
- operational alert thresholds
- runbook guidance for denial spikes and execution anomalies
