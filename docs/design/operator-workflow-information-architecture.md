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

## Request Composer Contract

The request composer is a governed submission control, not a chat box.

### Composer layout

The composer keeps source identity visible in the same frame as the request draft.

Desktop layout should treat the composer as a bounded work surface within the main workflow region:

- a source-and-posture header that stays visually attached to the draft
- the natural-language request field as the dominant editable control
- supporting helper text that explains governed submission expectations
- a compact action row for preview submission and allowed draft-level secondary actions

On narrower screens, these elements may stack, but they should remain a single composer surface
rather than dissolving into a transcript feed or disconnected controls.

### Composer controls

The primary editable control is a natural-language request field sized for multi-line operator
prompts, revisions, and clarification before preview.

The primary submit action must use governed language such as Submit for preview.

The composer may expose helper text for governed submission, but it must not offer raw-SQL entry.

Allowed secondary controls are limited to draft-safe actions such as clear draft, reopen as new
draft, or explicit source-fork entry points when those actions are available.

Free-form chat metaphors such as Send, message bubbles, or assistant-avatar framing are out of scope for this composer.

### Source identity and submission posture

The composer header should make three things obvious before submission:

- the currently bound source identity
- the governed submission posture, including that preview precedes any later execution step
- whether the draft is editable, reopened from history, or blocked by missing trusted prerequisites

Source identity and submit posture should remain visible without forcing the operator to open a
separate side panel just to confirm where the request will go.

If the draft was reopened from prior history, the composer should preserve lineage context and show
whether the source is still historical read-only lineage or a newly created forked draft.

### In-flight and blocked states

While preview submission is in flight, the composer keeps the draft visible, locks mutable controls, and surfaces a non-success status until an authoritative outcome returns.

The in-flight surface may show progress text, an inline pending indicator, and a disabled primary
action, but it must not imply preview success before the authoritative request or candidate record
exists.

If source binding, policy posture, or trusted submission prerequisites are missing, the composer must stay blocked and explain the missing prerequisite rather than implying that submission succeeded.

Blocked state messaging should stay attached to the composer so the operator can see which draft is
being held and what must be fixed before preview can be requested.

### Attachment posture

Attachment support is not implemented in this issue.

If attachments are shown at all, they must appear only as a disabled or omitted affordance with explicit out-of-scope copy.

## History Information Model

History entities are authoritative workflow records, not transcript messages.

The shell history model uses three distinct row types so operators can navigate prior work without
reducing everything to a generic session list.

### Request record

A request record represents one natural-language question submission and its request-scoped operator
intent.

Visible request metadata should include:

- request label with a short natural-language summary
- source identity at the time the request was made
- lifecycle state for the request, such as drafting, previewed, blocked, or superseded
- recency label derived from the authoritative request timestamp
- whether the request has later candidate or run descendants

The request row is the operator's entry point for reopening or revising prior work.

### Candidate record

A candidate record represents one server-owned SQL preview artifact linked directly to a single
request.

Visible candidate metadata should include:

- candidate label that makes preview identity explicit
- source identity bound to the candidate
- lifecycle state such as preview ready, blocked, expired, invalidated, or approved for execution
- guard posture and review anchor details, including candidate identity and SQL hash or equivalent
- recency label derived from the authoritative candidate timestamp

Candidate rows must stay distinct from request rows because multiple candidates may exist for one
request over time.

### Run record

A run record represents one attempted or completed execution of a specific candidate.

Visible run metadata should include:

- run label that distinguishes execution history from preview history
- source identity for the executed or attempted scope
- lifecycle state such as executing, succeeded, empty, denied, or failed
- result posture, for example rows returned, no rows, blocked before execution, or execution error
- recency label derived from the authoritative run timestamp

Run rows must never be inferred from transcript ordering alone. They are separate execution facts
anchored to an authoritative run record.

### Labels and Ordering

History labels should distinguish request, candidate, and run rows instead of flattening them into one generic session label.

Default history ordering is newest-first by the authoritative record timestamp for each row type.

When the shell groups related rows, the request is the parent anchor and linked candidate and run
records appear only from explicit authoritative relationships. Do not infer lineage from proximity,
display order, or similar wording alone.

If derived badges or summary text drift from the authoritative lifecycle record, the shell should
recalculate the surface from the authoritative request, candidate, or run state instead of
redefining the outcome around the stale summary.

### Left Rail Visibility

The left rail should show enough metadata for safe navigation without expanding into a full detail
pane.

Every visible history row should expose:

- row type label: Request, Candidate, or Run
- concise title or summary
- source identity
- lifecycle state
- recency label

The selected row may also expose a compact secondary line for guard posture, run outcome, or reopen
availability, but it should still read as navigation memory rather than full detail content.

### Supporting Detail Surfaces

When a history row is selected, supporting detail surfaces should reveal the anchored metadata for
that exact record and only its directly linked context.

Supporting details should include:

- authoritative record identifier for the selected request, candidate, or run
- source identity and source status
- lifecycle state and the timestamp that established that state
- direct parent or child links, such as request to candidate or candidate to run
- review or execution-specific metadata, such as SQL hash, guard status, or run outcome

Supporting surfaces should not generalize evidence or recommendations from one candidate or run to
its siblings unless the system has an explicit authoritative link that says the broader context
applies.

### Reopen Behavior

A request can reopen into a new active draft while preserving prior candidates and runs as immutable history.

Reopen means:

- the operator starts a new active request derived from the prior request intent
- prior candidate and run records remain closed historical facts and do not mutate into the new
  draft
- the reopened draft links back to the request it came from so the operator can compare lineage
- any later preview creates a new candidate record rather than reusing or editing a previous
  candidate in place
- any later execution creates a new run record tied to the newly selected candidate

Reopen must therefore create a new active workflow record, not resurrect an old candidate or treat
result history as if it were the current draft.

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

### Source selector lifecycle semantics

The source selector is interactive only while the operator is in an active draft with no bound preview candidate yet. In that state, it is used to choose the draft's initial source; changing to a different source must use an explicit draft-fork action rather than replacing the bound source in place.

State contract:

- draft with no preview yet: the operator may choose the draft's initial source before submitting
  into preview; switching to a different source must use an explicit draft-fork action that creates
  a new draft context
- previewed, approved, executing, and executed states: the selected source is displayed as bound
  identity, not as an editable control
- historical rows opened for review: the row shows the source that was bound to that request,
  candidate, or run at the time it became authoritative
- reopened history draft: the shell keeps the historical source binding visible as lineage and does
  not silently substitute a different source

After preview is created, the selected source becomes read-only bound identity for that draft, its candidate records, and any later execution or history surfaces derived from it.

Changing source from an unpreviewed draft must always be an explicit draft-fork action that creates a new draft context.

That explicit source-change action may carry forward the natural-language question only if the UI
states that choice clearly, but it must not carry forward the prior candidate, guard posture,
approval metadata, execution eligibility, or result history as if they still applied.

The shell must clear preview, guard, execution, and result surfaces that belonged to the previous source binding instead of silently retargeting them.

Reopening history into a new draft preserves the historical source binding as visible read-only lineage.

To work against a different source after history reopen, the operator must explicitly start a separate new draft or explicit fork rather than editing the bound source in place.

The UI must not silently switch sources after preview, approval, execution, or history reopen.

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
