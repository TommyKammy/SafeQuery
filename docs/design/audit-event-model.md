# Audit Event Model

## Purpose

This document defines the baseline event model for application-owned SafeQuery auditing.

## Audit Principles

- audit events are application-owned
- PostgreSQL is the authoritative audit store
- MLflow traces or runs may mirror engineering-relevant events, but they are supplemental
- MLflow mirrors must follow the approved export contract and must not become a shadow result or audit store
- third-party logs are supplemental only
- event records should support reconstruction and review
- result payloads should be minimized to reduce secondary data exposure

## Baseline Events

The baseline event taxonomy is:

- `query_submitted`
- `retrieval_requested`
- `retrieval_completed`
- `generation_requested`
- `generation_completed`
- `generation_failed`
- `guard_evaluated`
- `execution_requested`
- `execution_started`
- `execution_completed`
- `execution_denied`
- `execution_failed`
- `analyst_response_rendered`
- `request_rate_limited`
- `concurrency_rejected`
- `candidate_invalidated`

## Required Common Fields

Every audit event should include:

- event ID
- event type
- event timestamp
- correlation or request lineage identifiers
- causation event ID when applicable
- user identity
- session ID
- claim or role snapshot
- request ID
- retrieval corpus version if available
- retrieved asset identifiers if available
- analyst or explanation mode version if available
- query candidate ID if available
- candidate owner subject if available
- adapter version if available
- guard version if available
- schema snapshot version if available
- application version if available

## State and Event Alignment

The normative lifecycle state vocabulary lives in [query-lifecycle-state-machine.md](./query-lifecycle-state-machine.md).

This audit document defines event names, not competing state names. Baseline alignment:

- `query_submitted` aligns with `submitted`
- `retrieval_requested` and `retrieval_completed` cover retrieval activity that may occur before or alongside generation
- `generation_requested` and `generation_completed` bracket `generating`
- `guard_evaluated` closes `guard_running`
- approval metadata is established after a guard allow decision when the candidate is persisted before preview
- `execution_requested` maps to the `previewed -> execution_requested` transition
- `execution_started` maps to `execution_requested -> executing`
- `execution_denied` maps to denial at or after `execution_requested`
- `candidate_invalidated` maps to `approved -> invalidated` or `previewed -> invalidated`
- `analyst_response_rendered` records the answer package shown to the user when analyst mode is enabled

## Event-Specific Notes

### query_submitted

Should capture:

- natural language request
- authenticated session context

Natural-language input should be treated as potentially sensitive business data.

### generation_completed

Should capture:

- generated SQL hash
- canonical SQL or stored reference to it
- model or prompt version if applicable

### guard_evaluated

Should capture:

- allow or deny outcome
- denial codes if denied
- approval timestamp and approval expiration timestamp if allowed

### retrieval_completed

Should capture:

- retrieval corpus version
- retrieved asset identifiers
- retrieval authorization scope
- citation candidates returned to the response composer

### execution_denied

Should capture:

- primary deny code
- candidate state at denial time if available
- whether denial was caused by approval expiry, replay, ownership mismatch, entitlement change, or invalidation

### analyst_response_rendered

Should capture:

- analyst or explanation mode version
- citations rendered to the user
- which answer segments were labeled as executed evidence versus narrative guidance

### request_rate_limited and concurrency_rejected

Should capture:

- affected phase such as generate or execute
- applied limit key such as subject or session
- configured threshold identifier

### execution_completed

Should capture:

- execution duration
- row count returned
- column metadata summary
- result truncation indicators

### execution_failed

Should capture:

- failure category
- failure summary
- execution duration if available

## Result Storage Guidance

The baseline recommendation is:

- do not store full result sets in the audit store by default
- prefer row count, column metadata, duration, and error summaries
- store fuller result payloads only if separately justified and controlled

## Retention, Redaction, and Access Control

The audit store is a sensitive store.

The baseline posture should define:

- who may read raw audit records
- what fields are redacted or tokenized in lower-privilege views
- how long raw records are retained
- how deletion or legal-hold exceptions are managed

## Why this model matters

This event model improves:

- incident review
- reproducibility
- model and guard change analysis
- pilot governance
