#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

target_doc="docs/design/operator-workflow-information-architecture.md"

if [[ ! -f "$target_doc" ]]; then
  echo "missing operator workflow IA contract: $target_doc" >&2
  exit 1
fi

required_regex_patterns=(
  "^# Operator Workflow Information Architecture$"
  "^## Purpose$"
  "^## Workflow Principles$"
  "^## Screen Regions$"
  "^## Request Composer Contract$"
  "^## History Information Model$"
  "^## Primary Workflow$"
  "^## Screen Model by State$"
  "^## UX Issue Contract$"
)

required_literal_patterns=(
  "The operator shell is workflow-first, not transcript-first."
  "Left rail history"
  "History entities are authoritative workflow records, not transcript messages."
  "### Request record"
  "### Candidate record"
  "### Run record"
  "A request can reopen into a new active draft while preserving prior candidates and runs as immutable history."
  "Default history ordering is newest-first by the authoritative record timestamp for each row type."
  "History labels should distinguish request, candidate, and run rows instead of flattening them into one generic session label."
  "Source identity"
  "lifecycle state"
  "recency label"
  "Source identity"
  "Question composition"
  "SQL preview"
  "Guard review"
  "Result inspection"
  "### Source selector lifecycle semantics"
  "The source selector is interactive only while the operator is in an active draft with no bound preview candidate yet. In that state, it is used to choose the draft's initial source; changing to a different source must use an explicit draft-fork action rather than replacing the bound source in place."
  "After preview is created, the selected source becomes read-only bound identity for that draft, its candidate records, and any later execution or history surfaces derived from it."
  "Changing source from an unpreviewed draft must always be an explicit draft-fork action that creates a new draft context."
  "The shell must clear preview, guard, execution, and result surfaces that belonged to the previous source binding instead of silently retargeting them."
  "Reopening history into a new draft preserves the historical source binding as visible read-only lineage."
  "To work against a different source after history reopen, the operator must explicitly start a separate new draft or explicit fork rather than editing the bound source in place."
  "The UI must not silently switch sources after preview, approval, execution, or history reopen."
  "Do not collapse the shell into a generic chat transcript layout."
  "The request composer is a governed submission control, not a chat box."
  "### Composer layout"
  "### Composer controls"
  "### Source identity and submission posture"
  "### In-flight and blocked states"
  "### Attachment posture"
  "The composer keeps source identity visible in the same frame as the request draft."
  "The primary submit action must use governed language such as Submit for preview."
  "Free-form chat metaphors such as Send, message bubbles, or assistant-avatar framing are out of scope for this composer."
  "The composer may expose helper text for governed submission, but it must not offer raw-SQL entry."
  "Attachment support is not implemented in this issue."
  "If attachments are shown at all, they must appear only as a disabled or omitted affordance with explicit out-of-scope copy."
  "While preview submission is in flight, the composer keeps the draft visible, locks mutable controls, and surfaces a non-success status until an authoritative outcome returns."
  "If source binding, policy posture, or trusted submission prerequisites are missing, the composer must stay blocked and explain the missing prerequisite rather than implying that submission succeeded."
  "This document defines the shell contract for later UX-1 issues."
)

forbidden_literal_patterns=(
  "the operator may choose or replace the source before submitting into"
  "The request composer is a chat box."
  "The primary submit action should use Send."
)

for pattern in "${required_regex_patterns[@]}"; do
  if ! grep -Eq "$pattern" "$target_doc"; then
    echo "$target_doc missing required pattern: $pattern" >&2
    exit 1
  fi
done

for pattern in "${required_literal_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$target_doc"; then
    echo "$target_doc missing required text: $pattern" >&2
    exit 1
  fi
done

for pattern in "${forbidden_literal_patterns[@]}"; do
  if grep -Fq "$pattern" "$target_doc"; then
    echo "$target_doc contains forbidden conflicting text: $pattern" >&2
    exit 1
  fi
done
