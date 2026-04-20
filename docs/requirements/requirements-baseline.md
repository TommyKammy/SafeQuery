# Requirements Baseline

## Purpose

This document defines the initial requirements baseline for SafeQuery.

It translates the project brief and fixed stack decisions into a requirements-oriented form that can be used for backlog creation, design review, and implementation planning.

## Product Goal

SafeQuery must provide a controlled enterprise workflow that allows authenticated internal users to:

- submit natural language questions through a custom web UI
- receive candidate SQL from a replaceable SQL generation engine
- inspect generated SQL and guard results before execution
- execute only approved read-only queries against a constrained Microsoft SQL Server dataset

The product goal is not generic chat-with-data convenience. The goal is controlled, auditable, enterprise-safe NL2SQL.

## In-Scope Capabilities

The initial phase baseline is split into:

- a required core SafeQuery control-plane path
- optional feature-flagged extension tracks that may be enabled in the same phase if governance and safety requirements are satisfied

The required core path must support:

- custom web-based query submission
- enterprise user authentication
- application-owned session and authorization handling
- pluggable SQL generation through an internal adapter boundary
- application-owned SQL validation and safety enforcement
- preview-before-execute interaction
- read-only SQL execution against one constrained SQL Server dataset
- application-owned audit logging
- application-owned evaluation assets for quality measurement
- pilot-safety execution controls such as result limits and kill switch behavior

The initial phase may also enable these optional extension tracks behind explicit feature flags:

- application-owned governed search over approved semantic knowledge assets
- analyst-style answer composition grounded in governed search results and approved SQL execution
- MLflow-backed tracing, evaluation, and model-lifecycle support for ML and LLM features

If an optional extension track is enabled in Phase 1, its related requirements in this document become mandatory for that deployment and must be included in audit, evaluation, and governance review.

## Functional Requirements

### FR-1 User access and identity

The system must authenticate internal users through a SAML 2.0-compatible enterprise identity provider using a bridge layer between the identity provider and the application.

The application must own:

- authenticated session establishment
- route protection
- authorization context

### FR-2 Natural language query submission

The frontend must allow an authenticated user to submit a natural language request for data.

The submitted request must be handled as auditable application input.

### FR-3 Replaceable SQL generation

The backend must call the SQL generation capability through an internal adapter interface.

The first implementation may use a Vanna-based adapter with a local LLM runtime, but the rest of the system must not depend on Vanna-specific UI or control logic.

The adapter must not hold production SQL Server credentials.

### FR-4 Adapter isolation and context supply

The SQL generation adapter may receive only curated schema and policy context owned by the application, such as:

- allow-listed views or tables
- column metadata
- business glossary content approved for generation context
- policy metadata needed to constrain generation

The adapter must not receive:

- production SQL Server credentials
- raw unrestricted schema inventory
- independent authority to execute business queries

### FR-5 Governed semantic retrieval

If the governed-search feature flag is enabled, the application must provide Cortex Search-like governed retrieval over approved semantic assets such as:

- business glossary content
- schema and metric definitions
- approved analytic playbooks
- curated example questions and explanations

This retrieval capability must be application-owned, auditable, and subject to dataset governance and authorization rules.

Retrieved content must be treated as advisory context, not as independent execution authority.

### FR-6 Analyst-style orchestration

If the analyst feature flag is enabled, the application must provide Analyst-like orchestration that combines:

- governed retrieval over approved semantic assets
- SQL generation through the internal adapter boundary
- application-owned guard evaluation
- result explanation and citation rendering

The analyst experience must not bypass preview, guard, execution integrity, or audit requirements.

### FR-7 Application-owned SQL Guard

Before any execution attempt, the application must validate generated SQL using application-owned safety controls.

The guard baseline must support:

- read-only enforcement
- multi-statement rejection
- object allow-list enforcement
- fully-qualified object validation
- denial of cross-database and linked-server access
- denial of temp object creation and mutation-oriented syntax
- result-size and execution-time policy evaluation
- explicit allow or deny outcome

### FR-8 Human review before execution

Users must be able to inspect:

- the original natural language request
- the generated SQL
- the SQL Guard outcome

Execution must require an explicit user-visible approval step when the guard allows execution.

In the baseline terminology, this user-visible step is the execution request or confirmation step. It is distinct from the system approval metadata created when a guard-allowed candidate is persisted before preview.

In Phase 1, previewed SQL is not user-editable in place.

If edited SQL is supported later, the edited text must create a new candidate and trigger a fresh guard evaluation before any execution path becomes available.

### FR-9 Query approval and execution integrity

The execution API must not accept raw SQL text from the client.

Execution must be driven by a server-issued `query_candidate_id` that resolves to a stored candidate containing:

- opaque and unguessable candidate ID material
- canonicalized SQL
- SQL hash
- owner subject
- authorization snapshot
- guard status
- guard version
- schema snapshot version
- approval timestamp
- approval expiration timestamp
- execution count
- max execution count
- invalidated timestamp if invalidated
- invalidation reason if invalidated

The backend must execute only the stored canonical SQL associated with an approved, unexpired, non-invalidated candidate.

Canonicalization and any required row-bounding rewrite must complete before guard evaluation so that guard outcome, SQL hash, preview text, and execute-time SQL all refer to the same canonical SQL.

At execution time, the backend must re-check:

- that the current authenticated subject matches the candidate owner
- that the current authorization context still satisfies execution policy
- that execution count has not exceeded the allowed replay policy

The Phase 1 baseline should use `max_execution_count = 1` unless a tighter or broader replay rule is explicitly approved.

The transition that claims execution rights and increments `execution_count` must be atomic so that only one request can successfully claim a single-use candidate.

### FR-10 Controlled SQL execution

The backend must execute approved queries through an application-owned execution path using a dedicated read-only SQL Server login.

The system must not authenticate end users directly to SQL Server.

The Phase 1 execution contract is:

- the previewed SQL is the executable bounded canonical SQL
- if row-limiting rewrites are applied, they are applied before preview and become part of the canonical SQL and SQL hash
- byte limits, timeout, cancellation, and delivery truncation are enforced by runtime delivery controls without mutating SQL at execution time

Execution behavior must enforce baseline operational limits, including:

- max rows
- max bytes returned
- timeout
- query cancellation support
- global execute kill switch

### FR-11 Authentication, session, and authorization model

The trusted backend must remain the authoritative enforcement point for:

- session establishment and validation
- CSRF protection for state-changing actions
- default-deny authorization
- claim-to-role mapping
- execution entitlement checks

The frontend must not become an alternate trusted execution backend.

Role or entitlement changes must cause execution-time revalidation of previously approved candidates.

### FR-12 Dataset governance

The pilot dataset must be governed by an application-owned allow-list.

The baseline governance model must define:

- who approves exposed datasets
- who owns security review for sensitive data handling
- who applies allow-list updates in the application
- whether exposure is limited to approved views
- how sensitive columns are excluded or masked
- how schema drift is detected and reviewed
- how exception requests are approved and recorded
- whether the pilot uses one shared dataset contract or role-scoped contracts

The default pilot posture should be one shared dataset contract for all pilot users unless a role-scoped contract is explicitly documented and approved.

Governance for retrieval assets must also define:

- who owns each approved retrieval asset class such as glossary content, metric definitions, and playbooks
- who performs security review for retrieval content and citation visibility
- who applies approved retrieval corpus updates in application-managed indexing or configuration
- which documents or semantic assets are eligible for indexing
- who approves analyst-facing explanations or playbooks
- how retrieval assets are versioned and invalidated when source truth changes
- how retrieval authorization scope is mapped to application roles

### FR-13 Audit logging

The application must store durable audit records for all important lifecycle events, including:

- authenticated user identity
- natural language request
- generated SQL
- guard decision
- execution decision
- execution metadata
- errors and denials

The audit model must also preserve enough versioning metadata to support reconstruction, such as:

- event ID and event lineage
- session ID
- claim or role snapshot
- candidate owner
- adapter version
- guard version
- model or prompt version
- schema snapshot version

Because natural language inputs may contain sensitive business context, the audit database must be treated as a sensitive store with explicit retention, redaction, and access-control policy.

Retrieval and analyst experiences must also record:

- retrieval corpus version
- retrieved asset identifiers
- explanation template or analyst mode version if applicable

### FR-14 ML and LLM observability plane

If the MLflow integration feature flag is enabled, the application must integrate MLflow only as an engineering observability and evaluation plane for ML, LLM, retrieval, and analyst-style components.

This integration may record:

- request and component traces
- retrieval and tool-call spans
- prompt and model version lineage
- evaluation runs and regression results
- model registry metadata for auxiliary ML components

MLflow must not become the authoritative source of truth for:

- execution approval
- SQL Guard decisions
- candidate ownership or replay protection
- application authorization state
- authoritative audit retention

The MLflow integration contract must also define:

- which fields may be exported by default
- which fields are prohibited from export
- what redaction or tokenization profile applies before export
- what retention and access-control posture applies to engineering traces and runs
- how MLflow trace identifiers link back to authoritative PostgreSQL audit records without replacing them

### FR-15 Evaluation capability

The system must support application-owned evaluation assets so that NL2SQL quality can be measured independently of any one SQL generation engine.

Evaluation must include at least:

- execution match
- answer correctness
- deny correctness
- regression stability

The evaluation specification must also define:

- scenario taxonomy
- gold answer representation
- expected deny codes where relevant
- pass thresholds
- manual review rules for ambiguous outcomes

Evaluation for search and analyst capabilities should also include:

- retrieval relevance
- citation correctness
- explanation groundedness
- evidence-to-narrative consistency

If MLflow is enabled, evaluation results should be exportable to MLflow runs or experiments without making MLflow the only location where release-gating logic can be reconstructed.

### FR-16 Result delivery and caching posture

The baseline result-delivery posture must define:

- whether browser responses use `no-store` or equivalent cache prevention
- whether export or download is disabled in Phase 1
- whether admin or audit UIs may re-expose result data and at what granularity
- how search indexing and similar secondary exposure is prevented

Analyst-style answer cards must clearly distinguish:

- retrieved knowledge citations
- generated SQL
- executed result-backed claims
- non-executed narrative guidance

## Non-Functional Requirements

### NFR-1 Trust boundary clarity

The trusted control boundary must remain inside the application.

Authentication integration, authorization, guard logic, execution control, and audit logging must not be delegated to the SQL generation engine.

### NFR-2 Replaceability

The SQL generation component must be replaceable without major redesign of:

- frontend UX
- audit model
- authorization model
- SQL Guard
- execution path
- application persistence

### NFR-3 Least privilege

The first PoC must use least-privilege data access through:

- one SQL Server database
- one dedicated read-only application login
- one narrow allow-listed dataset
- no direct adapter path to production SQL Server

### NFR-4 Auditability

The system must preserve a durable and reviewable audit trail suitable for enterprise governance and debugging.

### NFR-5 Observability portability

The observability and evaluation plane should remain replaceable and should not create vendor lock-in around ML/LLM lifecycle operations.

### NFR-6 Narrow first release scope

The first release must remain intentionally constrained and avoid broad platform ambitions such as:

- multi-database query support
- write workflows
- BI/dashboard platform scope
- production HA architecture

### NFR-7 Pilot safety

Even in PoC scope, the system must include enough safety controls for pilot operation, including:

- bounded result delivery
- execution kill switch
- rate limiting
- concurrency limits
- auditable denial and failure paths

Generate and execute paths should have separate rate limits keyed by at least authenticated subject and session, with optional source-network controls if needed.

### NFR-8 Reproducibility

The system should preserve enough event and version metadata to explain why a candidate was allowed, denied, or executed.

### NFR-9 Policy-change safety

Policy, entitlement, or kill-switch changes must not leave stale approved candidates silently executable.

## Constraints

The initial implementation must remain consistent with the fixed stack:

- Next.js and TypeScript for the frontend
- FastAPI and Pydantic v2 for the backend
- PostgreSQL for application-owned persistence
- Microsoft SQL Server as the target business data source
- pyodbc as the initial SQL Server driver
- SQLAlchemy 2.x and Alembic for application-owned persistence
- a local LLM runtime for the initial SQL generation adapter

## Acceptance Lens for Future Issues

Future GitHub issues derived from this baseline should be framed so they make clear:

- whether the work belongs to the trusted application boundary
- whether the work belongs to a replaceable adapter boundary
- how the work preserves preview-before-execute behavior
- how the work preserves auditability and least privilege
- how the work preserves candidate-based execution integrity
- how the work handles policy-change invalidation and ownership binding

## Status

This document is the initial requirements baseline for the SafeQuery PoC and should be used together with the technology stack baseline and ADR set.
