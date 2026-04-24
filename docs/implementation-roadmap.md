# SafeQuery Implementation Roadmap

## Purpose

This roadmap summarizes the current implementation sequence after Epic A and its first documentation and UX follow-up work.

It records approved direction for the next implementation steps without treating optional extensions as prerequisites for the core SafeQuery control path.

## Current State

- Epic A established the initial repository shell, local dev baseline, and first end-to-end project framing.
- Epic A follow-up work hardened docs, repository hygiene, CI checks, and source-aware planning foundations.
- UX-1 established the operator-workflow information architecture and UI-foundation contract so the product shell can move beyond the Epic A state demo.

## Next Core Track

### 1. Multi-source foundation hardening

Focus areas:

- introduce the target source registry
- separate application PostgreSQL from any future business PostgreSQL source path
- define distinct secret names and connection identities for application PostgreSQL, business PostgreSQL, and SQL Server
- add source-aware smoke checks and telemetry
- add safeguards that prevent accidental execution against application PostgreSQL

### 2. Operator shell implementation against the UX-1 contract

Focus areas:

- replace the Epic A state demo with a workflow-first operator shell
- implement left-rail history for request, candidate, and run navigation
- implement explicit source visibility and source-selector lifecycle semantics
- implement stable preview, guard, and result panel contracts
- keep attachments out of the MVP unless separately approved

### 3. Source-aware core control path

Focus areas:

- make request, candidate, and execution records source-aware
- add source-aware entitlement checks and invalidation behavior
- add per-source dataset contracts and schema snapshot handling
- make adapter requests source-scoped and registry-driven
- keep single-source execution as a hard invariant

### 4. Connector and guard rollout

Focus areas:

- keep the SQL Server connector as the first active business-source connector
- add PostgreSQL business-source connector work on a separate path from application PostgreSQL persistence
- add dialect-aware canonicalization and guard profiles
- extend deny corpus and evaluation coverage per source family

### 5. Core vertical slice completion

Focus areas:

- complete preview-before-execute for the active source-aware path
- complete source-aware audit and evaluation
- complete result controls, kill switch behavior, and replay-safe execution handling
- ship a core vertical slice that stays application-owned from request to execution

## Optional Extension Tracks

These tracks remain optional and may begin only after the source-aware core path is stable enough for their dependencies:

- governed search
- analyst-style orchestration
- MLflow-backed engineering observability and evaluation support

If an optional track is enabled, its governance, audit, and evaluation requirements become mandatory for that deployment.

## Later Family Expansion

After the two-source core path is stable:

1. onboard `mysql`
2. evaluate `mariadb` as a sibling or delta profile
3. add Aurora as source flavors on top of PostgreSQL or MySQL families
4. define `oracle` as long-range planned metadata only, then onboard it last
   after Oracle-specific connector, dialect, guard, audit, entitlement,
   candidate lifecycle, operator-history, and release-gate reconstruction
   requirements are approved together

Each later family must be added through source-registry onboarding plus connector, guard, and evaluation profile work rather than through a trusted-control-plane redesign.
