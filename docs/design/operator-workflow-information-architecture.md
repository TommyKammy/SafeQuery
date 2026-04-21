# Operator Workflow Information Architecture

## Purpose

This document defines the workflow-first operator shell for SafeQuery. It describes the stable
information architecture, screen regions, and state-by-state work surfaces that replace a generic
demo shell with a product-facing application contract.

The operator shell is workflow-first, not transcript-first.

This document defines the product shell and screen contract only. It does not introduce backend
integration, real execution behavior, or production-complete interaction details.

## Visual Contract Alignment

[DESIGN.md](../../DESIGN.md) is the visual contract for this shell.

- Use `DESIGN.md` for surface hierarchy, spacing rhythm, typography, tone, and component posture.
- Use this document for workflow regions, state transitions, and what must stay visible together.
- If a future change alters both information architecture and visual treatment, update both documents
  intentionally so the workflow-first shell stays coherent.

## Workflow Principles

- Center the screen on the governed query workflow rather than a chat transcript.
- Keep source visibility and Source identity present before, during, and after question handling.
- Preserve a visible separation between Question composition, SQL preview, Guard review, and Result
  inspection.
- Require preview-before-execute in the information architecture. Execution belongs later in the
  workflow and must never visually imply automatic approval.
- Keep history, active work, and support context in distinct surfaces so the operator can maintain
  orientation during long review sessions.
- Do not collapse the shell into a generic chat transcript layout.

## Screen Regions

The default desktop shell uses three persistent regions.

### Left rail history

The left rail history is the operator's navigation memory. It holds:

- prior query sessions and recent work items
- lightweight status markers such as blocked, previewed, executed, or empty
- saved or pinned workflow entries when later issues define that behavior
- route entry points for new query work, source selection, and result revisits

The left rail is not a message transcript. It is a workflow history and navigation index.

### Main work surface

The main work surface holds the active step in the current workflow. At any moment it should make
one primary job obvious:

- compose the question
- review the generated SQL
- review the guard outcome
- inspect the returned results

Only one of those jobs should dominate the main surface at a time, even if nearby context remains
visible.

### Support surfaces

Support surfaces hold contextual information that should remain visible without overtaking the main
task. They can appear as a right rail, stacked side panels, or bounded drawers depending on screen
size. Typical support content includes:

- Source identity and source status
- guard rationale and denial or warning details
- execution eligibility or preview metadata
- audit anchors, timestamps, and future operator guidance

## Source Visibility

Source visibility is a first-class shell concern, not a secondary detail inside result content.

The operator must be able to identify:

- which source or governed dataset the question is targeting
- whether the source is currently available for querying
- whether the shown SQL preview and results belong to that same source binding

Source identity should remain visible across the workflow so the operator does not lose scope when
moving from composition to preview to results.

Source identity should appear in a stable, repeated location such as the frame header, a pinned
support panel, or both. It must not disappear when the main work surface switches from composition
to preview or results.

## Primary Workflow

The canonical operator path is:

1. Select or confirm the active source.
2. Enter or refine a natural-language question.
3. Submit the question into preview.
4. Review the generated SQL and guard outcome before any later execution step.
5. Trigger execution only from an explicit reviewed state when future issues add that capability.
6. Inspect results or empty-state outcomes while retaining access to the original question, source,
   and review context.

This sequence should read like a governed work process, not like an open-ended assistant
conversation.

## Screen Model by State

### New query state

- Left rail history shows recent sessions and a clear "new query" entry.
- Main work surface prioritizes source confirmation and Question composition.
- Support surfaces show source metadata, operator guidance, and empty placeholders for downstream
  preview and guard context.

### SQL preview state

- Left rail history keeps the in-progress item selected and preserves nearby prior work.
- Main work surface switches from composition to SQL preview.
- Support surfaces show Guard review, source details, and the preview contract metadata needed for
  later execution.
- Preview metadata should include the server-owned candidate identity, SQL hash or equivalent review
  anchor, and approval or expiry context when those fields exist.

### Guarded or blocked state

- Main work surface stays anchored to the current query item rather than redirecting the operator
  into a generic error conversation.
- Support surfaces explain why execution remains closed and what prerequisite or policy caused the
  block.
- If required review metadata or trusted backend signals are missing, the shell should stay blocked
  rather than implying that execution can proceed.
- Left rail history keeps the failed attempt as a workflow item so the operator can revise or
  compare without losing continuity.

### Result inspection state

- Main work surface focuses on Result inspection, including bounded rows or explicit no-data
  outcomes.
- Support surfaces keep the reviewed SQL, guard posture, source context, and execution metadata
  visible.
- Result presentation should distinguish executed result-backed evidence from advisory notes,
  source-description context, or future analyst-style guidance.
- Left rail history keeps the item available for revisit and comparison with later runs.

## Transition Rules

- The shell should maintain a consistent frame while the main work surface changes by workflow
  state.
- Source identity, current item identity, and workflow status should persist across transitions.
- Preview and guard context must remain visible when results appear; results do not replace the
  review history.
- Empty or blocked outcomes should preserve the same workflow framing instead of sending the user
  back to a blank start screen.

## Responsive Model

- Desktop keeps left rail history, main work surface, and support surfaces visible as separate
  zones.
- Tablet may stack support surfaces below the main work surface, but the left rail history or its
  condensed equivalent must remain distinct from the active work surface.
- Mobile may collapse the layout into stacked regions, but the order should remain: navigation and
  history, active work surface, support context.

## UX Issue Contract

This document defines the shell contract for later UX-1 issues.

Later issues should refine, not replace, these boundaries:

- source selector behavior and source-status presentation
- history information model and grouping behavior
- composer interactions and submission affordances
- preview panel details and SQL review behavior
- guard panel contents and severity presentation
- result panel structure, empty state handling, and revisit behavior

If a later proposal conflicts with this shell model, update this document intentionally rather than
silently drifting the operator workflow back toward a transcript UI.
