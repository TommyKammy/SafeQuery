# Issue #61: [B-2] Implement source registry activation, deactivation, and blocked posture handling

## Supervisor Snapshot
- Issue URL: https://github.com/TommyKammy/SafeQuery/issues/61
- Branch: codex/issue-61
- Workspace: .
- Journal: .codex-supervisor/issues/61/issue-journal.md
- Current phase: reproducing
- Attempt count: 1 (implementation=1, repair=0)
- Last head SHA: 02cf32412c737b9350fca1828e3a9e0b3767cfc3
- Blocked reason: none
- Last failure signature: none
- Repeated failure signature count: 0
- Updated at: 2026-04-21T15:06:00.795Z

## Latest Codex Summary
- None yet.

## Active Failure Context
- None recorded.

## Codex Working Notes
### Current Handoff
- Hypothesis: The source registry only stores `activation_posture` as an unconstrained string today, so SafeQuery cannot authoritatively distinguish executable vs non-executable posture at the backend enforcement boundary.
- What changed: Added a focused posture test, introduced an explicit `SourceActivationPosture` enum plus a fail-closed `ensure_source_is_executable` service check, and tightened the registry scaffold/model coverage so persistence only admits `active`, `paused`, `blocked`, and `retired`.
- Current blocker: none
- Next exact step: Commit the focused registry posture checkpoint and continue from implementing callers that need to enforce the executable-source boundary.
- Verification gap: No integration caller uses `ensure_source_is_executable` yet; this turn only establishes the posture model and service boundary required by the issue.
- Files touched: backend/app/db/models/source_registry.py; backend/app/services/source_registry.py; backend/tests/test_source_registry_models.py; backend/tests/test_source_registry_posture.py; backend/alembic/versions/0002_source_registry_scaffold.py
- Rollback concern: The Alembic scaffold now persists `activation_posture` as an explicit non-native enum/check-constrained field instead of a freeform string; future migrations must preserve those four values or add a migration when expanding posture states.
- Last focused command: PYTHONPATH=backend python3 -m pytest backend/tests/test_source_registry_posture.py backend/tests/test_source_registry_models.py
### Scratchpad
- Keep this section short. The supervisor may compact older notes automatically.
