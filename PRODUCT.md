# Product

## Register

product

## Users

SafeQuery is used by authenticated internal operators, reviewers, and governance owners who need to turn business questions into reviewed, auditable SQL-backed answers. They work in a controlled enterprise context where source identity, candidate state, guard posture, evidence, and execution eligibility must stay visible before any query can run.

## Product Purpose

SafeQuery provides a governed NL2SQL operator workflow. It accepts a natural language question, binds it to an approved business source, generates a candidate through an isolated adapter, validates the candidate through application-owned controls, and executes only reviewed read-only candidates. Success means the operator can approve or block work from business-readable evidence while technical SQL, audit, and export boundaries remain traceable.

## Brand Personality

Calm, precise, governed. The product should feel like controlled operational tooling, not a chat demo or a SQL generator showcase.

## Anti-references

Avoid chat-first database demos, vendor-owned SQL generation UIs, neon cybersecurity styling, decorative dashboard chrome, and flows that make raw SQL the primary business approval object. Do not imply that support bundles, handoff exports, LLM output, search results, or analyst summaries can authorize execution.

## Design Principles

- Keep the workflow source-bound: source identity and candidate lineage stay visible near every review or execution decision.
- Make business review primary: answer plans, guard posture, citations, and lifecycle state lead before raw SQL.
- Fail closed in the UI: missing candidate, source, guard, or entitlement context must read as blocked or draft-only.
- Preserve technical traceability: authorized reviewers can inspect SQL and audit details without exposing them through support or export surfaces.
- Separate advice from authority: supplemental analyst or retrieval context can explain, but only server-owned candidate and run records govern execution.

## Accessibility & Inclusion

Target WCAG AA contrast for operational text and controls. Keep keyboard-visible focus states, use semantic controls for progressive disclosure, support reduced-motion preferences, and avoid color-only status communication.
