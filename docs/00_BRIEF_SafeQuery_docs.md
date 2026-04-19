# 00_BRIEF_SafeQuery_docs.md

## Purpose

This brief defines the documentation baseline that Codex Supervisor must use when generating the initial documentation set for **SafeQuery**.

SafeQuery is a secure enterprise NL2SQL proof of concept. The system allows authenticated internal users to submit natural language questions through a custom web UI, generate candidate SQL through a replaceable SQL generation engine, validate that SQL through strict application-owned safety controls, and execute only approved read-only queries against a constrained Microsoft SQL Server dataset.

The purpose of this brief is to ensure that all generated documentation is:
- architecturally consistent
- aligned with already-fixed stack decisions
- explicit about trust boundaries
- explicit about what is application-owned vs engine-owned
- suitable for later conversion into GitHub issues, ADRs, and design docs

---

## Project Name

**SafeQuery**

---

## Project Objective

Build a secure enterprise NL2SQL PoC with the following characteristics:

- custom web UI
- enterprise authentication
- strict application-owned governance and safety controls
- read-only Microsoft SQL Server access
- replaceable SQL generation engine
- full application-owned audit logging
- explicit preview-before-execute workflow
- narrow and controlled dataset exposure

This project is not intended to be a generic chat-with-database demo. It is intended to be a **controlled, auditable, enterprise-safe NL2SQL system**.

---

## Fixed Stack Decisions

The following stack decisions are already fixed and must be reflected consistently across all generated docs.

### Frontend
- **Next.js**
- **TypeScript**

### Authentication
- **Okta SAML**
- SAML must be abstracted through a **bridge layer**
- Prefer architecture phrasing such as:
  - Okta SAML → SAML bridge → application
- Do not assume direct raw SAML implementation inside the core application unless explicitly discussing rejected alternatives

### Backend
- **FastAPI**
- **Pydantic v2**

### Application Database
- **PostgreSQL**
- PostgreSQL is the system of record for application-owned records such as:
  - audit logs
  - evaluation assets
  - internal metadata
  - future control-plane persistence if needed

### Target Business Data Source
- **Microsoft SQL Server**
- SQL Server access uses a **read-only local login**
- End users do not authenticate directly to SQL Server through the product

### SQL Server Driver Strategy
- Initial implementation: **pyodbc**
- Future evaluation track: **mssql-python**
- Do not present mssql-python as the current primary path

### ORM / Persistence
- **SQLAlchemy 2.x**
- **Alembic**

### SQL Generation Engine
- The system must use a **pluggable SQL generation interface**
- Initial implementation: **Vanna-based adapter**
- Vanna is used only as an **initial SQL generation adapter**
- Vanna is **not** part of the trusted control boundary
- Vanna-specific UI, audit, filtering, and authorization must not be treated as core architecture

### Local Model Runtime
- Use a **local LLM runtime**
- Do not assume managed external model APIs as the primary baseline

### SQL Validation / Safety
- SQL validation is **application-owned**
- SQL Guard is **application-owned**
- Filtering is **application-owned**
- Execution approval is **application-owned**
- Execution control is **application-owned**

### Audit
- Audit logging is **application-owned**
- Audit system of record is **PostgreSQL**
- Third-party engine logs are supplemental only

---

## Architectural Principles

All generated documentation must preserve the following principles.

### 1. Application-owned trust boundary
The trusted control boundary belongs to the application, not to the SQL generation engine.

The application owns:
- identity integration
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

The architecture must make it possible to replace the initial Vanna-based adapter later without major redesign of:
- UI
- authentication flow
- RBAC
- audit model
- SQL Guard
- execution path
- application database model

### 3. Least-privilege database access
The Microsoft SQL Server connection must be constrained through:
- a dedicated read-only application login
- a narrow allow-listed dataset
- preferably controlled views or a limited set of approved tables
- application-owned guardrails before execution

### 4. Human-visible review before execution
The first PoC is intentionally semi-automatic.

Users must be able to:
- submit a natural language request
- inspect generated SQL
- inspect guard outcome
- explicitly trigger execution only when allowed

### 5. Auditability is mandatory
Auditability is a first-class requirement, not an optional enhancement.

The system must record:
- authenticated user identity
- natural language input
- generated SQL
- guard decision
- execution decision
- execution metadata
- errors and denials

### 6. Narrow first-phase scope
The first phase must remain intentionally small and safe.

Assume:
- one SQL Server database
- one constrained allow-listed dataset
- a small pilot user group
- no write access
- no broad self-service data platform goals

---

## Explicit Non-Goals

Generated documentation must remain consistent with these non-goals.

- no direct end-user SQL Server authentication
- no write access to SQL Server
- no dependency on Vanna UI
- no dependency on Vanna audit logs as the system of record
- no dependency on Vanna filtering or authorization features
- no automatic execution of unreviewed SQL
- no multi-database query support in the initial phase
- no production HA/scaling design in the first doc baseline
- no broad BI/dashboarding scope in the initial phase
- no architecture that makes Vanna a non-replaceable core dependency

---

## Documentation Goals

Codex Supervisor should generate a documentation baseline that helps the team:

- understand the fixed stack and why it was chosen
- understand the trust boundary and control-plane ownership
- understand the difference between application-owned responsibilities and replaceable engine responsibilities
- align later GitHub issues with already-fixed architecture decisions
- create a strong foundation for requirements docs, ADRs, and design docs

The initial documentation set should emphasize:
- clarity
- consistency
- architecture ownership
- replaceability
- safety boundaries
- enterprise realism

---

## Required Initial Documentation Set

Codex Supervisor should generate the first documentation baseline around the following categories.

### 1. Documentation index / reading order
Examples:
- `docs/README.md`
- `docs/01_READING_ORDER.md`

### 2. Requirements baseline
Examples:
- `docs/requirements/requirements-baseline.md`
- `docs/requirements/technology-stack.md`

### 3. ADR set
Examples:
- `docs/adr/ADR-0001-frontend-backend-split.md`
- `docs/adr/ADR-0002-auth-bridge-with-okta-saml.md`
- `docs/adr/ADR-0003-sql-server-driver-strategy.md`
- `docs/adr/ADR-0004-postgresql-as-app-system-of-record.md`
- `docs/adr/ADR-0005-pluggable-sql-generation-engine.md`

### 4. High-level design set
Examples:
- `docs/design/system-context.md`
- `docs/design/container-view.md`
- `docs/design/runtime-flow.md`

Do not jump directly into detailed design for every subsystem before establishing the baseline requirement and architecture decisions.

---

## Documentation Writing Rules

All generated docs must follow these writing rules.

### Language
- English only

### Format
- Markdown
- copy-paste ready
- repository-ready
- no placeholder sections unless clearly intentional
- no unexplained TODO-heavy drafts

### Style
- concise but concrete
- architecture-oriented
- explicit about ownership and trust boundaries
- avoid vague marketing language
- avoid buzzword-heavy writing
- prefer direct engineering language

### Consistency
- use the same terms consistently across all docs
- do not alternate between conflicting names for the same component
- do not describe Vanna as a trusted control-plane component
- do not describe the SQL generation engine as owning auth, filtering, audit, or execution control

### Design quality
- rejected alternatives may be mentioned, but must be clearly labeled as rejected or not selected
- future options may be mentioned, but must not weaken the baseline decision
- do not invent new core stack choices that conflict with this brief

---

## Required Terminology Conventions

Use the following terminology consistently.

### Preferred terms
- **application-owned**
- **trusted control boundary**
- **pluggable SQL generation engine**
- **initial Vanna-based adapter**
- **read-only local login**
- **allow-listed dataset**
- **preview-before-execute**
- **system of record**
- **replaceable adapter boundary**

### Avoid or limit
- “AI agent” as the primary framing
- “chatbot” as the primary product term
- “autonomous query execution”
- “self-service BI platform”
- wording that implies uncontrolled or unsupervised DB access

---

## Required Architectural Positioning of Vanna

Codex Supervisor must preserve the following interpretation:

- Vanna is an **initial implementation detail** of the SQL generation adapter layer
- Vanna is **not** the system architecture center
- Vanna is **not** the trusted control plane
- Vanna is **not** the system of record for audit or authorization
- Vanna-specific optional features must not be presented as the baseline governance model
- the architecture must remain viable even if Vanna is replaced later

This point is important and should be reflected clearly in requirements, ADRs, and design docs.

---

## Required Architectural Positioning of the Auth Layer

Codex Supervisor must preserve the following interpretation:

- enterprise identity source: **Okta**
- federation protocol source: **SAML**
- application-facing integration should be expressed through a **bridge layer**
- the application should not be documented as deeply SAML-centric unless discussing protocol boundaries or rejected alternatives
- authorization is not delegated to the auth bridge

---

## Required Architectural Positioning of SQL Server Access

Codex Supervisor must preserve the following interpretation:

- the application uses one or more tightly controlled read-only DB connections
- end users do not directly authenticate to SQL Server through the product
- the target dataset is constrained and allow-listed
- direct unrestricted schema exposure is out of scope
- execution is always mediated by the application

---

## Required Output Quality

The generated documentation should be good enough that it can be used as the basis for:

- future docs-related GitHub issues
- implementation planning
- ADR reviews
- repo bootstrap documentation
- design discussions with other engineers
- later detailed design docs

This means the documents must not be shallow summaries. They should express:
- architecture intent
- ownership boundaries
- rationale
- constraints
- assumptions
- non-goals

---

## Forbidden Shortcuts

Codex Supervisor must avoid the following shortcuts.

- do not collapse auth/authz/audit/guard into a vague “security layer”
- do not treat Vanna as the owner of safety or governance
- do not omit the adapter/replaceability concept
- do not treat PostgreSQL as optional scratch storage only
- do not describe pyodbc and mssql-python as equally current baseline choices
- do not skip rationale sections when defining key stack decisions
- do not write docs that assume future production scale requirements are already fixed
- do not propose architectural shortcuts that weaken preview-before-execute
- do not assume unrestricted SQL access for convenience

---

## Suggested First Execution Order

If Codex Supervisor needs an execution order for generating the first documentation set, prefer:

1. `docs/README.md`
2. `docs/01_READING_ORDER.md`
3. `docs/requirements/requirements-baseline.md`
4. `docs/requirements/technology-stack.md`
5. ADR set
6. `docs/design/system-context.md`
7. `docs/design/container-view.md`
8. `docs/design/runtime-flow.md`

---

## Final Instruction

Generate the initial SafeQuery documentation baseline so that:
- the stack decisions already fixed in this brief are preserved
- trust boundaries are explicit
- replaceability of the SQL generation engine is explicit
- application-owned governance and safety responsibilities are explicit
- the docs are ready to serve as the foundation for later GitHub issues and implementation work