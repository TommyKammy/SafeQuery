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
- the SQL generation engine must be **replaceable**
- the initial SQL generation implementation uses a **Vanna-based adapter**
- the initial scope is a **single SQL Server database** with a constrained allow-listed dataset
- generated SQL must be reviewed and validated before execution

---

## Design Principles

The baseline stack must preserve the following architectural principles.

### 1. Application-owned trust boundary
The trusted control boundary belongs to the application, not to the SQL generation engine.

The application is responsible for:
- authentication integration
- session handling
- authorization
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
- configuration-related persistence if needed
- future operational state required by the control plane

PostgreSQL is the system of record for application-owned persistence.

### Why this choice
- durable and extensible foundation for audit-heavy internal records
- better long-term fit than lightweight local-only storage
- suitable for future admin screens, search, and analytics needs
- independent from both the SQL generation engine and the target MSSQL business data source

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

### Why this choice
- supports enterprise-sensitive use cases
- fits self-hosted and controllable architecture goals
- reduces exposure of prompts and metadata to external services

---

## SQL Guard and Execution Safety

The application implements a fully **application-owned SQL Guard** layer.

SQL Guard is responsible for validating generated SQL before execution and acts as the primary safety boundary between SQL generation and SQL execution.

SQL Guard enforces strict read-only behavior, including:
- statement-type restrictions
- object allow-list enforcement
- multi-statement rejection
- execution limit policies
- structured allow/deny decisions

Approved SQL is executed only through an **application-owned execution path** using least-privilege SQL Server credentials.

Execution authority is never delegated to the SQL generation engine.

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
- exact session and token handling model
- exact frontend-to-backend boundary and BFF responsibilities
- exact PostgreSQL schema design for audit and evaluation storage
- SQL Guard rule specification in full detail
- exact MSSQL dataset exposure model
- mssql-python evaluation criteria and migration decision gate
- deployment topology and runtime hardening details

---

# Status

This document defines the **current baseline technology stack** for the SafeQuery PoC and should be treated as the reference point for subsequent requirements, ADRs, architecture documents, and implementation planning.
