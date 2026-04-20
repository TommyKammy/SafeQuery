# Issue #8: [A-7] Implement the custom web UI skeleton for the query workflow

## Supervisor Snapshot
- Issue URL: https://github.com/TommyKammy/SafeQuery/issues/8
- Branch: codex/issue-8
- Workspace: .
- Journal: .codex-supervisor/issues/8/issue-journal.md
- Current phase: reproducing
- Attempt count: 1 (implementation=1, repair=0)
- Last head SHA: 7cf0b5006907aa82ae4ddc3044c9a7e9ad7c21af
- Blocked reason: none
- Last failure signature: none
- Repeated failure signature count: 0
- Updated at: 2026-04-20T08:34:17.848Z

## Latest Codex Summary
- Replaced the baseline landing page with a SafeQuery-owned query workflow shell that follows `DESIGN.md`, exposes visible sign-in/query/preview/results/empty/error states, and keeps question input, SQL preview, guard status, and results on separate surfaces. Added focused Vitest coverage for the page states and verified with `npm test -- --run app/page.test.tsx` plus `npm run build` using explicit frontend API env vars.

## Active Failure Context
- None recorded.

## Codex Working Notes
### Current Handoff
- Hypothesis: The current failure was simply absence of the required custom workflow shell; proving it with a focused page test before implementation would keep the change bounded.
- What changed: Added a Vitest frontend harness, wrote focused page-state tests, implemented `QueryWorkflowShell` with visible sign-in/query/preview/results/empty/error states, rewired `app/page.tsx` to drive the shell from `searchParams`, and replaced the baseline styling with `DESIGN.md`-aligned tokens and layout.
- Current blocker: none
- Next exact step: Commit the verified checkpoint on `codex/issue-8`, then open or update the draft PR if requested by the supervisor flow.
- Verification gap: Manual browser inspection was not run in this turn; automated state coverage and production build passed locally.
- Files touched: `frontend/app/page.tsx`, `frontend/components/query-workflow-shell.tsx`, `frontend/app/globals.css`, `frontend/app/layout.tsx`, `frontend/app/page.test.tsx`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/vitest.config.ts`, `frontend/vitest.setup.ts`
- Rollback concern: Low; changes are isolated to the frontend shell and test setup, with no auth or backend execution wiring introduced.
- Last focused command: `API_INTERNAL_BASE_URL=http://127.0.0.1:8000 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run build`
### Scratchpad
- Keep this section short. The supervisor may compact older notes automatically.
