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

## Future Connector Threat Model

This section records threat-model requirements for planned connector families
before any activation candidate is selected. It is documentation only: it does
not add runtime connector behavior, local services, driver dependencies, or
active execution coverage.

SafeQuery remains the application-owned trusted control boundary for source
registration, connector selection, dialect and guard profile selection, secrets
resolution, candidate lifecycle checks, result bounding, and audit records.
External systems, database drivers, adapter output, request metadata, hostnames,
connection strings, MLflow traces, analyst artifacts, and operator-facing labels
are not authority sources. No planned family or flavor may dispatch connector
code until the source registry and activation gate approve the family or flavor
with connector, guard, audit, runtime, secrets, dataset, row-bound, and
evaluation evidence together.

### MySQL

MySQL is planned metadata only. The backend-owned source registry must select
`source_family=mysql`, connector profile, dialect profile, secret indirection,
dataset contract, schema snapshot, and activation posture before any MySQL
source can become an activation candidate.

| Connector risk | Activation blocker | Mitigation requirement |
| --- | --- | --- |
| dialect ambiguity between MySQL modes, generated SQL, adapter hints, driver names, and hostname or URL shapes | missing backend-selected MySQL dialect profile, guard profile, and drift coverage | select MySQL only from the source registry; require MySQL-aware canonicalization, unsafe `sql_mode` rejection, deny corpus coverage, and profile-version drift tests |
| privilege scope that can expose cross-database objects, system catalogs, temporary object mutation, or write paths | missing read-only database identity and approved dataset contract | require least-privilege read-only credentials, approved schema snapshot linkage, entitlement posture, and denies for writes, cross-database references, system catalog access, and temporary mutation |
| driver behavior around connection timeout, statement timeout, cancellation, retry classification, and cursor/result materialization | missing runtime readiness for the selected backend-owned connector profile | prove driver availability, connect timeout, statement timeout, cancellation probe, source-unavailable classification, and no retry for malformed or policy-denied states |
| secret handling through raw connection strings, placeholder credentials, client-supplied connection material, or application PostgreSQL reuse | missing secrets readiness | resolve only backend-owned secret indirection such as a per-source reader handle; reject placeholder credentials, sample secrets, raw credentials, and application PostgreSQL credential reuse |
| result bounds using implicit driver defaults, unsafe `LIMIT` or `OFFSET`, or unbounded reads | missing row-bounds readiness | enforce one policy-bounded `LIMIT`; allow `OFFSET` only with an explicit bounded `LIMIT`; audit truncation state and deny conflicting or missing row bounds |
| audit evidence that cannot reconstruct the selected source, connector profile, dialect profile, guard version, or primary deny code | missing audit and release-gate reconstruction readiness | emit SafeQuery-owned source-aware audit events and evaluation evidence for source id, family, flavor, dataset contract, schema snapshot, execution policy, connector profile, dialect profile, guard version, request id, candidate id, approval id, and primary deny code |

### MariaDB

MariaDB is a distinct planned `source_family=mariadb` profile, not an
adapter-inferred MySQL alias. It may share MySQL-family concepts only where a
backend-owned MariaDB profile explicitly approves them.

| Connector risk | Activation blocker | Mitigation requirement |
| --- | --- | --- |
| dialect ambiguity from MySQL overlap, MariaDB mode and version drift, executable comments, optimizer hints, driver names, and connection labels | missing MariaDB-specific dialect and guard readiness | require a separate MariaDB delta profile, canonicalization drift coverage, MariaDB deny fixtures, and no silent MySQL guard reuse |
| privilege scope that exposes information schema, system catalogs, cross-database objects, write paths, or temporary/session mutation | missing MariaDB dataset-contract and privilege evidence | require a least-privilege read-only MariaDB identity, approved dataset contract, approved schema snapshot, entitlement posture, and deny fixtures for writes and unauthorized metadata access |
| driver behavior that differs from MySQL for timeouts, cancellation, retry posture, result cursor handling, or version-specific behavior | missing MariaDB runtime readiness | prove backend-owned connector selection, driver availability, timeout, cancellation, source-unavailable classification, and malformed or denied state handling for MariaDB specifically |
| secret handling through MySQL secret reuse, raw URLs, placeholder credentials, or client-supplied connection material | missing MariaDB secrets readiness | require backend-owned MariaDB secret indirection and reject MySQL credential reuse unless the authoritative profile explicitly binds the same controlled source |
| result bounds that assume MySQL behavior without MariaDB delta review | missing MariaDB row-bounds readiness | require one policy-bounded `LIMIT`, explicit bounded `LIMIT` for `OFFSET`, MariaDB delta tests, truncation metadata, and deny behavior for unsafe bounds |
| audit evidence that collapses MariaDB into MySQL or omits profile-version proof | missing MariaDB audit and release-gate reconstruction readiness | preserve `source_family=mariadb`, optional flavor, dataset contract, schema snapshot, execution policy, connector profile, dialect profile, guard version, and primary deny code in SafeQuery-owned audit and evaluation artifacts |

### Aurora PostgreSQL

Aurora PostgreSQL is a planned flavor of the PostgreSQL family. Its authoritative
identity is `source_family=postgresql` plus
`source_flavor=aurora-postgresql` in the backend-owned source registry.

| Connector risk | Activation blocker | Mitigation requirement |
| --- | --- | --- |
| dialect ambiguity from treating Aurora PostgreSQL as a top-level family or from trusting hostnames, driver names, request hints, generated SQL, or adapter output | missing authoritative flavor binding and PostgreSQL inheritance evidence | resolve the flavor only from the source registry; inherit PostgreSQL generation, canonicalization, guard, deny corpus, and row-bounding behavior only when the registry says so |
| privilege scope across Aurora cluster endpoints, replicas, databases, schemas, or application PostgreSQL identity | missing Aurora PostgreSQL connector-profile and dataset-contract evidence | require read-only backend-owned connector identity, explicit cluster or instance endpoint posture, approved schema snapshot, entitlement posture, and separation from application PostgreSQL credentials |
| driver behavior that changes timeout, cancellation, TLS, failover, replica, or source-unavailable semantics | missing Aurora PostgreSQL runtime readiness | reverify PostgreSQL driver behavior against Aurora endpoint posture, engine version, TLS posture, connection timeout, statement timeout, cancellation probe, and retry classification |
| secret handling through reused PostgreSQL application credentials, raw cluster URLs, placeholders, or client-provided connection material | missing Aurora PostgreSQL secrets readiness | require backend-owned flavor-specific secret indirection and reject application PostgreSQL secrets, placeholder credentials, raw connection strings, and request-provided material |
| result bounds that rely on generic PostgreSQL behavior without Aurora flavor regression coverage | missing Aurora PostgreSQL row-bounds readiness | preserve PostgreSQL bounded canonical SQL behavior and add Aurora flavor regressions for row bounds, truncation metadata, timeout, and cancellation |
| audit evidence that cannot distinguish business PostgreSQL from Aurora PostgreSQL | missing Aurora PostgreSQL audit and release-gate reconstruction readiness | include source id, `source_family=postgresql`, `source_flavor=aurora-postgresql`, dataset contract, schema snapshot, execution policy, connector profile, dialect profile, guard version, endpoint posture evidence, and primary deny code |

### Aurora MySQL

Aurora MySQL is a planned flavor of the MySQL family. Because MySQL remains
planned metadata only, Aurora MySQL cannot become executable before MySQL family
activation is approved.

| Connector risk | Activation blocker | Mitigation requirement |
| --- | --- | --- |
| dialect ambiguity from treating Aurora MySQL as a top-level family or from trusting hostnames, driver names, request hints, generated SQL, connection URLs, or adapter output | missing authoritative flavor binding and approved MySQL-family readiness | resolve `source_family=mysql` and `source_flavor=aurora-mysql` only from the source registry; inherit MySQL behavior only after MySQL family profiles are approved |
| privilege scope across Aurora cluster endpoints, replicas, databases, system catalogs, or write paths | missing Aurora MySQL connector-profile and dataset-contract evidence | require read-only backend-owned connector identity, explicit cluster or instance endpoint posture, approved schema snapshot, entitlement posture, and MySQL-family deny coverage |
| driver behavior that changes timeout, cancellation, TLS, failover, replica, or source-unavailable semantics | missing Aurora MySQL runtime readiness | reverify MySQL driver behavior against Aurora endpoint posture, engine version, TLS posture, connection timeout, statement timeout, cancellation probe, and retry classification |
| secret handling through MySQL secret reuse without an explicit source binding, raw cluster URLs, placeholders, or client-provided connection material | missing Aurora MySQL secrets readiness | require backend-owned flavor-specific secret indirection and reject placeholder credentials, raw connection strings, and request-provided material |
| result bounds that assume MySQL behavior without Aurora flavor regression coverage | missing Aurora MySQL row-bounds readiness | preserve the approved MySQL bounded `LIMIT` posture and add Aurora MySQL regressions for row bounds, truncation metadata, timeout, and cancellation |
| audit evidence that cannot prove the Aurora MySQL flavor or underlying MySQL profile versions | missing Aurora MySQL audit and release-gate reconstruction readiness | include source id, `source_family=mysql`, `source_flavor=aurora-mysql`, dataset contract, schema snapshot, execution policy, connector profile, dialect profile, guard version, endpoint posture evidence, and primary deny code |

### Oracle

Oracle is long-range planned metadata only. Oracle support must not activate
connector dispatch, runtime defaults, local startup services, guard behavior, or
release-gate coverage until a distinct Oracle source-family gate is approved.

| Connector risk | Activation blocker | Mitigation requirement |
| --- | --- | --- |
| dialect ambiguity from Oracle version differences, quoted identifier case, PL/SQL, database links, package/session state, connection descriptors, driver names, request hints, generated SQL, or adapter output | missing Oracle-specific dialect and guard readiness | require Oracle-aware canonicalization, explicit quoted identifier handling, a distinct fail-closed guard profile, and denies for PL/SQL, procedure execution, dynamic SQL, database links, package/session mutation, unsupported syntax, and profile drift |
| privilege scope that exposes schemas, packages, database links, system catalogs, external data access, or write paths | missing Oracle dataset-contract and least-privilege evidence | require read-only database identity, approved dataset contract, schema snapshot, entitlement posture, and deny fixtures for writes, metadata access, external access, database links, and session/package mutation |
| driver behavior around connect descriptors, wallets, TLS, service names, timeout support, cancellation, cursor materialization, and source-unavailable classification | missing Oracle runtime readiness | prove backend-owned Oracle connector selection, driver availability, wallet and TLS posture, connect timeout, statement timeout, cancellation probe, result materialization, and fail-closed retry classification |
| secret handling through raw descriptors, wallet material, placeholder credentials, sample secrets, or client-provided connection material | missing Oracle secrets readiness | resolve only backend-owned Oracle secret indirection for service name, username, wallet reference, and TLS posture; reject raw credentials, placeholder secrets, sample secrets, and client-supplied material |
| result bounds that rely on ambiguous `FETCH FIRST`, `ROWNUM`, pagination, or nested query behavior | missing Oracle row-bounds readiness | approve one canonical policy-bounded row-limit shape before guard, preview, and execution; test conflicting bounds, unbounded reads, truncation metadata, and audit reconstruction |
| audit evidence that cannot reconstruct Oracle connector identity, wallet reference posture, dialect profile, guard version, or deny reason | missing Oracle audit and release-gate reconstruction readiness | preserve source id, `source_family=oracle`, flavor, dataset contract, schema snapshot, execution policy, connector profile, dialect profile, guard version, wallet reference posture, request id, candidate id, approval id, and primary deny code in SafeQuery-owned audit and evaluation evidence |

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
