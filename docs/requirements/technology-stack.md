# Technology Stack Baseline

## Purpose

This document defines the baseline technology stack for **SafeQuery**, a secure enterprise NL2SQL proof of concept.

SafeQuery is designed to let authenticated internal users submit natural language questions through a custom web UI, generate candidate SQL through a replaceable SQL generation engine, validate that SQL through strict application-owned safety controls, and execute only approved read-only queries against a constrained Microsoft SQL Server dataset.

This document captures the **current baseline stack**, the **design intent behind each choice**, and the **architectural constraints** that must remain true during implementation.

---

## Scope

This document covers the baseline stack for:

- frontend application
- authentication and identity flow
- backend services
- application-owned persistence
- Microsoft SQL Server connectivity
- SQL generation engine integration
- governed semantic retrieval and analyst-style orchestration
- SQL Guard and execution safety
- audit logging
- evaluation harness
- observability
- testing and quality tooling

This document does **not** define full detailed design, deployment topology, or production scaling strategy.

---

## Assumptions

The current implementation assumptions are:

- the user-facing product is a **custom web application**
- enterprise authentication is required
- authentication must support a **SAML 2.0-compatible enterprise identity provider**
- SAML complexity should be abstracted through a **bridge layer**
- the backend is the trusted control plane of the system
- the application, not the SQL generation engine, owns governance and safety
- the target business data source is **Microsoft SQL Server**
- SQL Server access must use a **read-only local login**
- the initial SQL connectivity path uses **pyodbc**
- **mssql-python** may be evaluated later as a separate investigation track
- application-owned records such as audit logs must be stored in **PostgreSQL**
- **MLflow** may be used as an engineering plane for tracing, evaluation, and model lifecycle management
- the SQL generation engine must be **replaceable**
- the initial SQL generation implementation uses a **Vanna-based adapter**
- the initial scope is a **single SQL Server database** with a constrained allow-listed dataset
- generated SQL must be reviewed and validated before execution

The initial phase posture is:

- the core NL2SQL control path is required
- governed search and analyst-style capabilities are optional feature-flagged extension tracks in Phase 1
- MLflow integration is an optional feature-flagged engineering-plane integration in Phase 1
- if an optional track is enabled, its governance, audit, and evaluation requirements become mandatory for that deployment

---

## Design Principles

The baseline stack must preserve the following architectural principles.

### 1. Application-owned trust boundary
The trusted control boundary belongs to the application, not to the SQL generation engine.

The application is responsible for:
- authentication integration
- session handling
- authorization
- governed retrieval over approved semantic assets
- dataset exposure policy
- SQL validation
- execution approval
- execution control
- audit logging
- evaluation assets

### 2. Replaceable SQL generation engine
The SQL generation engine must be isolated behind an internal adapter boundary.

The system must be able to replace the initial Vanna-based implementation in the future without major changes to:
- frontend UI
- authentication flow
- session model
- RBAC model
- SQL Guard
- audit logging
- SQL execution path
- application-owned persistence

### 3. Least-privilege data access
Access to Microsoft SQL Server must be constrained through:
- a dedicated read-only application login
- a narrow allow-listed dataset
- preferably controlled views or a limited set of approved tables
- application-owned SQL validation before execution

### 4. Explicit human visibility before execution
The initial PoC is intentionally semi-automatic.

Users must be able to:
- submit a natural language request
- review generated SQL
- see guard decisions
- explicitly confirm execution only when allowed

### 5. Auditability as a core requirement
Auditability is not optional.

All meaningful lifecycle steps must be recorded by the application, including:
- authenticated user identity
- natural language request
- generated SQL
- guard decision
- execution decision
- execution result metadata
- errors and denials

### 6. Modern but stable implementation choices
The stack should favor technologies that are:
- modern enough to remain maintainable long term
- widely understood by engineers
- explicit in typing and interfaces
- compatible with enterprise security and operational requirements

---

## Non-Goals

The baseline stack does **not** aim to provide the following in the first phase:

- direct end-user database authentication
- write access to Microsoft SQL Server
- dependency on Vanna-specific UI
- dependency on Vanna-specific audit features as the system of record
- dependency on Vanna-specific filtering or authorization
- automatic execution of unreviewed SQL
- multi-database query support
- enterprise-wide rollout from day one
- production-grade HA or scaling architecture in this phase
- charting and advanced BI features in the first implementation
- tightly coupling core application behavior to a single SQL generation vendor or project
- requiring search, analyst orchestration, or MLflow integration for the first safe vertical slice of the core NL2SQL control path

---

# Baseline Technology Stack

## Frontend

The user-facing application is built with **Next.js** and **TypeScript**.

Next.js provides a modern and maintainable foundation for the custom web UI, including:
- query input flow
- SQL preview
- result rendering
- audit views
- future administrative screens

TypeScript is used throughout the frontend to improve maintainability, strengthen API contracts, and reduce ambiguity across application boundaries.

The frontend is fully **application-owned** and does not depend on UI components provided by the SQL generation engine.

### Why this choice
- modern and maintainable web application stack
- strong ecosystem and long-term support outlook
- suitable for custom enterprise UX and admin surfaces
- works well with a backend-owned control plane model

---

## Authentication and Identity

Enterprise authentication is handled through a **SAML 2.0-compatible identity provider**, bridged by an intermediate **SAML-to-OAuth/OIDC-compatible layer**.

This architecture intentionally avoids embedding full SAML protocol complexity directly into the application core.

The application consumes authenticated identity from the bridge layer and establishes its own:
- session model
- authorization context
- route protection behavior

Authentication confirms identity, while authorization remains an **application-owned concern**.

The baseline trusted-backend posture is:

- FastAPI is the authoritative trusted backend for execution-sensitive decisions
- Next.js is the application UI layer and must not expose an alternate raw-SQL execution path
- session and CSRF enforcement are application responsibilities, not bridge-only responsibilities
- claim-to-role mapping is default-deny and application-owned

### Why this choice
- reduces direct SAML protocol complexity inside the application
- preserves compatibility with enterprise identity requirements
- keeps authorization logic under application control
- improves maintainability relative to direct SAML-heavy app implementation

---

## Backend

The application backend is built with **FastAPI**.

FastAPI is used as the primary API and control-plane implementation for:
- query submission
- SQL generation orchestration
- SQL Guard evaluation
- execution approval
- SQL execution control
- audit logging
- administrative endpoints
- evaluation harness support

The backend owns all trusted control boundaries of the system.

The backend is also the only component permitted to:

- hold SQL Server execution credentials
- mint `query_candidate_id` records and approval TTLs
- bind previewed SQL to executable canonical SQL
- enforce kill switch, timeout, and result limits
- enforce candidate ownership and replay limits
- atomically claim single-use execution rights

### Why this choice
- strong fit for Python-based orchestration and validation logic
- natural fit for NL2SQL integration and SQL Guard implementation
- modern type-driven development model
- good long-term maintainability for service-layer responsibilities

---

## Configuration and Data Models

The backend uses **Pydantic v2** for:
- request models
- response models
- validation
- settings and configuration schemas

Application settings must be explicit, typed, and reviewable.

Critical settings such as:
- allowed datasets
- SQL execution limits
- adapter selection
- audit behavior
- environment-specific control settings

must be defined through application configuration rather than inferred from external engine behavior.

Retrieval-specific settings such as:

- indexed semantic asset sources
- retrieval authorization scope
- analyst explanation features
- citation rendering policy

must also be application-defined and reviewable.

### Why this choice
- explicit typing and validation improve maintainability
- reduces configuration ambiguity
- fits well with FastAPI and modern Python service design

---

## Application Database

The application uses **PostgreSQL** as its primary internal database.

PostgreSQL stores application-owned data such as:
- audit records
- evaluation cases
- internal metadata
- retrieval corpus metadata and indexing state if the application stores them locally
- configuration-related persistence if needed
- future operational state required by the control plane

PostgreSQL is the system of record for application-owned persistence.

### Why this choice
- durable and extensible foundation for audit-heavy internal records
- better long-term fit than lightweight local-only storage
- suitable for future admin screens, search, and analytics needs
- independent from both the SQL generation engine and the target MSSQL business data source

---

## ML and LLM Lifecycle Plane

The recommended engineering plane for ML, LLM, retrieval, and analyst-style lifecycle workflows is **MLflow**.

MLflow is used here for:

- tracing and observability of LLM and retrieval workflows
- evaluation run management
- prompt and model lineage tracking
- optional model registry support for auxiliary ML components such as rerankers or classifiers

MLflow is not the SafeQuery trusted control plane. It is an engineering support plane around experimentation, debugging, regression management, and lifecycle visibility.

### Why this choice
- strong fit for experiment tracking, evaluation comparison, and GenAI tracing
- useful for retrieval and analyst-style quality improvement loops
- keeps lifecycle tooling separate from execution governance
- remains compatible with vendor-neutral and self-hosted operation

---

## Target Data Source

The target business data source is **Microsoft SQL Server**, accessed through a dedicated **read-only local login** owned by the application.

The application does not connect to SQL Server using end-user credentials.

End users are never granted direct database execution authority through the product.

Access is intentionally constrained to a narrow, allow-listed dataset, preferably exposed through:
- controlled views
- or a limited set of approved tables

### Why this choice
- aligns with least-privilege principles
- keeps the first PoC small and understandable
- reduces accidental overexposure of business data
- preserves a clean separation between user identity and DB execution credentials

---

## SQL Server Driver Strategy

The initial SQL Server connectivity path uses **pyodbc**.

This is the primary and supported implementation for the first PoC phase due to:
- maturity
- ecosystem familiarity
- compatibility with established SQL Server connectivity patterns

In parallel, the project may evaluate **mssql-python** as a future alternative.

That evaluation is treated as a separate investigation track and must not block the initial implementation.

### Why this choice
- pyodbc is the stable delivery path
- mssql-python remains a future-looking option
- avoids premature commitment to an immature migration path
- preserves room for future driver strategy refinement

---

## ORM and Persistence Layer

The application uses **SQLAlchemy 2.x** as the primary persistence layer for application-owned data.

**Alembic** is used for schema migration management.

Application-owned persistence covers internal records such as:
- audits
- configuration state
- evaluation assets
- internal metadata

Application-owned persistence is intentionally separated from the execution path for generated SQL against Microsoft SQL Server.

### Why this choice
- strong long-term maintainability
- explicit control over schemas and migrations
- suitable for PostgreSQL-backed internal system records
- keeps internal control-plane data separate from user-generated SQL execution

---

## SQL Generation Engine

The application uses a **pluggable SQL generation interface** to isolate natural-language-to-SQL generation from the rest of the system.

The initial implementation is an **adapter backed by Vanna and a local LLM runtime**.

Vanna is used strictly as a **SQL generation component** and is not part of the system’s trusted control boundary.

The adapter must not hold production SQL Server credentials or direct execution authority. It should receive only curated schema context and policy-approved metadata supplied by the application.

The application remains the **system of record** for:
- authentication
- authorization
- dataset exposure policy
- SQL validation
- execution control
- filtering
- audit logging

Vanna-specific UI, audit, filtering, and authorization features are explicitly **out of scope** for the core architecture.

Any future migration from Vanna to another SQL generation engine must be achievable through the internal adapter boundary with minimal impact on the surrounding application layers.

The same replaceability expectation should apply to analyst-style orchestration components. Search and explanation features may help users understand data and results, but they do not become the trusted control plane.

### Why this choice
- enables practical delivery with an initial engine
- avoids engine lock-in
- preserves long-term replaceability
- aligns with application-owned safety and governance model

---

## Local LLM Runtime

The initial SQL generation adapter uses a **local LLM runtime** rather than a managed external model API.

This supports:
- enterprise privacy requirements
- controllable execution boundaries
- reduced dependency on external model services

The local LLM runtime is an implementation detail of the SQL generation adapter layer and does not receive any control-plane authority.

If the analyst experience uses local LLM inference for explanation, summarization, or retrieval-grounded answer composition, that logic remains advisory and application-governed rather than independently trusted.

### Why this choice
- supports enterprise-sensitive use cases
- fits self-hosted and controllable architecture goals
- reduces exposure of prompts and metadata to external services

## Governed Semantic Retrieval and Analyst Experience

SafeQuery may include features analogous to Snowflake Cortex Search and Analyst, but implemented within the SafeQuery trust model.

The baseline posture is:

- semantic retrieval is application-owned and limited to approved knowledge assets
- analyst-style answer composition is grounded in retrieved assets and approved SQL execution results
- retrieval and explanation layers do not bypass guard, execution integrity, dataset governance, or auditing
- citations should distinguish retrieved knowledge from executed result-backed evidence

Exact retrieval substrate is intentionally left open for later implementation choice. It may be backed by application-owned indexing in PostgreSQL or another approved retrieval component, but the trust boundary remains in the application.

### Why this choice
- gives users search-first and analyst-style experiences without moving governance into external tools
- improves discoverability of schema, metrics, and analytic guidance
- keeps trust, audit, and execution controls inside SafeQuery

---

## SQL Guard and Execution Safety

The application implements a fully **application-owned SQL Guard** layer.

SQL Guard is responsible for validating generated SQL before execution and acts as the primary safety boundary between SQL generation and SQL execution.

SQL Guard enforces strict read-only behavior, including:
- statement-type restrictions
- object allow-list enforcement
- multi-statement rejection
- cross-database and linked-server denial
- temp object and side-effecting syntax denial
- execution limit policies
- structured allow/deny decisions

Approved SQL is executed only through an **application-owned execution path** using least-privilege SQL Server credentials.

Execution authority is never delegated to the SQL generation engine.

In the first-phase execution path, the system should execute only canonical SQL stored against an approved `query_candidate_id` rather than accepting raw SQL text from the frontend at execution time.

The Phase 1 execution contract is that the previewed SQL is the executable bounded canonical SQL. If row-limiting rewrites are needed, they occur before preview and become part of the canonical SQL. Byte and timeout enforcement remain runtime delivery controls and must not silently rewrite SQL after approval.

Canonicalization and any required row-bounding rewrite must therefore complete before SQL Guard evaluation so that guard decision, SQL hash, preview text, and execute-time SQL all refer to the same canonical SQL.

### Why this choice
- preserves hard separation between generation and execution
- enables enforceable safety policy
- prevents optional engine features from becoming implicit control points
- supports future engine replacement without weakening safety controls

---

## Audit Logging

Audit logging is fully **application-owned** and stored in PostgreSQL.

Every significant step in the request lifecycle must be recorded, including:
- user identity
- natural language request
- generated SQL
- guard decision
- execution decision
- execution result metadata
- errors and denials

The audit record should also preserve reconstruction metadata such as adapter version, guard version, schema snapshot version, and prompt or model version where applicable.

If search and analyst capabilities are enabled, the audit record should also preserve retrieval corpus version, retrieved asset identifiers, and analyst or explanation mode version where applicable.

The audit store should be treated as a sensitive store because natural-language inputs, role context, and execution metadata may contain sensitive business information. Retention, redaction, and access controls are part of the baseline posture.

If MLflow is enabled, it may receive mirrored engineering traces or evaluation outputs, but PostgreSQL remains the authoritative audit system of record.

The application audit store is the authoritative system of record.

Third-party engine logging may be retained as supplemental debugging information, but it is not part of the system of record.

### Why this choice
- auditability is a core product requirement
- preserves compliance and operational review capability
- avoids dependence on optional third-party logging behavior
- supports future admin and governance workflows

---

## Evaluation Harness

The system includes an **engine-independent evaluation harness** for NL2SQL quality assessment.

Evaluation assets, including:
- test prompts
- expected outcomes
- regression cases

are application-owned and must remain reusable even if the SQL generation engine changes.

The initial implementation may run evaluations against the Vanna adapter, but the evaluation framework itself must not be tightly coupled to Vanna-specific internals.

The evaluation baseline should include a deny corpus, expected deny codes, and pilot entry thresholds rather than relying only on qualitative review.

If governed retrieval and analyst-style answers are enabled, the evaluation baseline should also measure retrieval relevance, citation correctness, and explanation groundedness.

If MLflow is enabled, it should be the default place to compare those evaluation runs across prompt, retrieval, and model variants.

### Why this choice
- enables repeatable quality measurement
- supports regression testing
- preserves engine comparison flexibility
- aligns with the replaceable-engine principle

---

## Observability

The application includes **application-owned observability** for core request flows, especially around:
- authentication
- SQL generation
- guard evaluation
- execution
- audit persistence

Tracing, structured logging, and operational metrics should be implemented at the application layer so that end-to-end behavior remains visible even if internal engine components are replaced later.

MLflow is the recommended backend for engineering-facing GenAI tracing and evaluation workflows, provided that trace export is configured so that sensitive data handling remains consistent with SafeQuery policy.

Pilot-safe execution controls such as kill switch state, timeouts, row limits, and cancellation outcomes should also be observable at the application layer.

Rate-limit rejections, concurrency rejections, candidate invalidation, and replay denials should also be observable at the application layer.

### Why this choice
- supports debugging and operational review
- preserves observability across replaceable internal components
- keeps core operational visibility under application control

---

## Testing and Quality Tooling

The backend test strategy uses **pytest** for unit and integration testing.

The frontend and end-to-end workflow should be validated through browser-based tests against the custom web UI and authentication flow.

Automated testing should cover:
- SQL Guard behavior
- adapter isolation
- audit persistence
- authorization boundaries
- query preview flow
- execution approval flow

Developer tooling should emphasize maintainability and consistency. Type checking, linting, formatting, migration management, and repeatable local environments are part of the baseline engineering quality standard.

### Why this choice
- supports safe iteration
- reduces regression risk
- aligns with long-term maintainability goals
- enforces consistency across a multi-layer architecture

---

# Architectural Summary

The SafeQuery stack is intentionally designed around a strict separation of responsibilities:

- the **frontend** owns user interaction
- the **authentication bridge and backend** own identity, authorization, and policy enforcement
- **PostgreSQL** owns internal system records such as audits and evaluation assets
- **SQL Server** remains a constrained read-only target data source
- the **SQL generation engine** is treated as a replaceable adapter, not as a control-plane authority
- the **application** remains the trusted owner of governance, safety, execution control, and auditability

This separation is a core design principle and must be preserved throughout implementation and future evolution.

---

# Open Follow-Up Topics

The following items are intentionally left for later design documents and ADRs:

- exact authentication bridge product configuration
- exact PostgreSQL schema design for audit and evaluation storage
- exact parser and AST implementation choice for SQL Guard
- numeric defaults for rate limits, TTLs, and result bounds
- exact admin and audit UI result re-exposure design
- exact MLflow deployment topology, retention, and redaction posture
- mssql-python evaluation criteria and migration decision gate
- deployment topology and runtime hardening details

---

# Status

This document defines the **current baseline technology stack** for the SafeQuery PoC and should be treated as the reference point for subsequent requirements, ADRs, architecture documents, and implementation planning.
