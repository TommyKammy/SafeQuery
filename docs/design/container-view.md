# Container View

## Purpose

This document describes the major runtime containers in SafeQuery and the responsibilities assigned to each one.

## Containers

### 1. Web frontend

Technology:

- Next.js
- TypeScript

Responsibilities:

- authenticated user interaction
- natural language request input
- governed search interactions
- analyst-style answer display with citations
- SQL preview and guard result display
- execution confirmation
- result rendering
- future audit and admin screens

Non-responsibilities:

- direct SQL Server access
- raw SQL execution submission
- storage of authoritative approval state

### 2. Application backend

Technology:

- FastAPI
- Pydantic v2

Responsibilities:

- API endpoints
- session-aware request handling
- authorization context
- governed retrieval orchestration
- analyst answer composition orchestration
- orchestration of SQL generation
- SQL Guard evaluation
- execution approval workflow
- SQL execution orchestration
- audit event creation
- candidate ID minting and approval TTL enforcement
- result limits, timeout, and cancellation enforcement
- kill switch enforcement

This backend is the core trusted control plane.

### 3. SQL generation adapter

Initial technology direction:

- internal adapter contract
- Vanna-based implementation
- local LLM runtime

Responsibilities:

- translate natural language request plus allowed context into candidate SQL

Non-responsibilities:

- production SQL Server credential ownership
- direct execution against the business database
- final authorization
- final execution authority
- system-of-record auditing

### 4. Application persistence store

Technology:

- PostgreSQL
- SQLAlchemy 2.x
- Alembic

Responsibilities:

- audit logs
- evaluation assets
- internal metadata
- retrieval corpus metadata and indexing state if stored locally
- future control-plane state

### 5. ML lifecycle plane

Technology:

- MLflow

Responsibilities:

- trace ML, LLM, retrieval, and analyst workflows
- store evaluation runs and regression comparisons
- manage prompt, model, and experiment lineage
- optionally register auxiliary ML models such as rerankers or classifiers

Non-responsibilities:

- authoritative audit retention
- SQL Guard enforcement
- execution approval
- candidate lifecycle authority

### 6. Governed retrieval corpus

Technology:

- application-owned semantic asset store or search index

Responsibilities:

- store or index approved glossary, schema, metric, and playbook assets
- serve authorized retrieval results for search and analyst experiences
- preserve source attribution and versioning

### 7. Target business database

Technology:

- Microsoft SQL Server
- read-only login for the application

Responsibilities:

- serve constrained approved business data for read-only query execution

### 8. Enterprise identity path

Components:

- SAML 2.0-compatible identity provider
- SAML bridge

Responsibilities:

- authenticate enterprise users before the application establishes its own session and authorization context

## Container Relationships

- The web frontend calls the FastAPI backend.
- The backend calls the SQL generation adapter to obtain candidate SQL.
- The backend may emit engineering traces and evaluation records to MLflow.
- The backend may retrieve approved semantic assets for search or analyst-style guidance.
- The backend validates generated SQL before any execution.
- The backend stores canonical SQL and approval state before exposing execution.
- The backend persists audit and internal records to PostgreSQL.
- The backend executes only approved read-only SQL against Microsoft SQL Server.
- The frontend never talks directly to SQL Server or to the SQL generation engine.

## Architectural Boundary Notes

- PostgreSQL is for application-owned records, not business query execution.
- MLflow is for engineering observability and evaluation, not authoritative governance or audit state.
- The retrieval corpus is for governed semantic context, not autonomous execution control.
- SQL Server is for constrained read-only business data access, not for app-owned audit state.
- The SQL generation adapter is replaceable and intentionally not trusted as the control plane.
