import { HealthStatusCard } from "./health-status-card";
import type { HealthSnapshot } from "../lib/health";

type WorkflowState =
  | "signin"
  | "query"
  | "preview"
  | "review_denied"
  | "completed"
  | "empty"
  | "execution_denied"
  | "failed"
  | "canceled"
  | "results"
  | "error";

type CanonicalWorkflowState =
  | "signin"
  | "query"
  | "preview"
  | "review_denied"
  | "completed"
  | "empty"
  | "execution_denied"
  | "failed"
  | "canceled";

type QueryWorkflowShellProps = {
  apiUrl: string;
  health: HealthSnapshot;
  question: string;
  state: WorkflowState;
};

type StateDefinition = {
  description: string;
  label: string;
};

type WorkflowContext = {
  candidateIdentity?: string;
  candidateState?: string;
  lifecycleTimestamp?: string;
  requestIdentity?: string;
  runIdentity?: string;
  runState?: string;
  sourceIdentity: string;
};

const workflowStates: Record<CanonicalWorkflowState, StateDefinition> = {
  canceled: {
    description: "Execution started from a reviewed candidate but stopped before the run completed.",
    label: "Canceled"
  },
  completed: {
    description: "Execution completed and returned bounded rows for the reviewed run record.",
    label: "Completed"
  },
  empty: {
    description: "Execution completed, but the reviewed run record returned no rows.",
    label: "Empty state"
  },
  execution_denied: {
    description: "The reviewed candidate was blocked at execute time and no execution payload was produced.",
    label: "Execution denied"
  },
  failed: {
    description: "Execution started for the reviewed run record but ended in a controlled failure state.",
    label: "Failed"
  },
  preview: {
    description: "The question has been staged for analyst review with generated SQL still in placeholder mode.",
    label: "SQL preview"
  },
  query: {
    description: "Compose a governed question and move into review without leaving the product shell.",
    label: "Query input"
  },
  review_denied: {
    description: "The request stopped during review before any execution run was allowed to start.",
    label: "Review denied"
  },
  signin: {
    description: "Reserved sign-in entrypoint before any real authentication bridge is wired.",
    label: "Sign in"
  }
};

const workflowStateAliases: Partial<Record<WorkflowState, CanonicalWorkflowState>> = {
  error: "review_denied",
  results: "completed"
};

const workflowStateOrder: CanonicalWorkflowState[] = [
  "signin",
  "query",
  "preview",
  "review_denied",
  "completed",
  "empty",
  "execution_denied",
  "failed",
  "canceled"
];

export function resolveWorkflowState(value?: string): CanonicalWorkflowState {
  if (!value) {
    return "query";
  }

  if (Object.prototype.hasOwnProperty.call(workflowStateAliases, value)) {
    return workflowStateAliases[value as WorkflowState] ?? "query";
  }

  if (Object.prototype.hasOwnProperty.call(workflowStates, value)) {
    return value as CanonicalWorkflowState;
  }

  return "query";
}

function buildStateHref(state: CanonicalWorkflowState, question: string): string {
  const params = new URLSearchParams({
    question,
    state
  });

  return `/?${params.toString()}`;
}

function getSqlPreview(question: string): string {
  return [
    "-- placeholder SQL generated from the question review surface",
    "SELECT vendor_name, SUM(quarterly_spend) AS quarterly_spend",
    "FROM approved_vendor_spend",
    `WHERE review_prompt = '${question.replace(/'/g, "''")}'`,
    "GROUP BY vendor_name",
    "ORDER BY quarterly_spend DESC",
    "LIMIT 10;"
  ].join("\n");
}

function getWorkflowContext(state: CanonicalWorkflowState): WorkflowContext {
  const sourceIdentity = "SAP spend cube / approved_vendor_spend";
  const requestIdentity = "req-sq-204";

  if (state === "preview" || state === "review_denied") {
    return {
      candidateIdentity: "candidate-sq-204",
      candidateState: state === "review_denied" ? "guard_denied" : "preview_ready",
      lifecycleTimestamp: state === "review_denied" ? "2026-04-21 14:24 JST" : "2026-04-21 14:18 JST",
      requestIdentity,
      sourceIdentity
    };
  }

  if (state === "query" || state === "signin") {
    return {
      sourceIdentity
    };
  }

  return {
    candidateIdentity: "candidate-sq-204",
    candidateState: "approved_previewed",
    lifecycleTimestamp:
      state === "completed"
        ? "2026-04-21 14:32 JST"
        : state === "empty"
          ? "2026-04-21 14:34 JST"
          : state === "execution_denied"
            ? "2026-04-21 14:31 JST"
            : state === "failed"
              ? "2026-04-21 14:35 JST"
              : "2026-04-21 14:33 JST",
    requestIdentity,
    runIdentity: "run-sq-204",
    runState:
      state === "completed"
        ? "executed"
        : state === "empty"
          ? "executed_empty"
          : state === "execution_denied"
            ? "execution_denied"
            : state === "failed"
              ? "execution_failed"
              : "execution_canceled",
    sourceIdentity
  };
}

function getGuardTone(state: CanonicalWorkflowState): string {
  if (state === "review_denied" || state === "execution_denied" || state === "failed") {
    return "danger";
  }

  if (state === "completed" || state === "empty") {
    return "success";
  }

  if (state === "canceled") {
    return "muted";
  }

  return "warning";
}

function getGuardHeadline(state: CanonicalWorkflowState): string {
  if (state === "review_denied") {
    return "Review denied before execution";
  }

  if (state === "completed") {
    return "Execution completed with rows";
  }

  if (state === "empty") {
    return "Execution completed with no approved rows";
  }

  if (state === "execution_denied") {
    return "Execution denied at execute time";
  }

  if (state === "failed") {
    return "Execution failed after run start";
  }

  if (state === "canceled") {
    return "Execution canceled before completion";
  }

  return "Awaiting analyst review";
}

function getGuardCopy(state: CanonicalWorkflowState): string {
  if (state === "review_denied") {
    return "The request never crossed into execution. Guard denial stays anchored to the candidate review record instead of being restyled as a run failure.";
  }

  if (state === "completed") {
    return "Result inspection stays tied to the reviewed candidate and run record so operators can distinguish executed evidence from nearby advisory context.";
  }

  if (state === "empty") {
    return "The result surface can represent a clean no-data outcome without restyling the rest of the page or hiding guard context.";
  }

  if (state === "execution_denied") {
    return "Execute-time checks revalidated ownership, approval freshness, and replay posture. The run stays denied instead of inferring success from an earlier preview.";
  }

  if (state === "failed") {
    return "The run record exists, but the payload is not trusted as successful output. The shell keeps the failure anchored to that run instead of showing speculative rows.";
  }

  if (state === "canceled") {
    return "Cancellation is distinct from denial and failure. The shell preserves run lineage and lifecycle context so the operator can see that execution started but did not finish.";
  }

  return "The first shell stops at review boundaries. No real auth, SQL generation, or execution path is trusted in this issue.";
}

function getResultTitle(state: CanonicalWorkflowState): string {
  if (state === "completed") {
    return "Completed result set";
  }

  if (state === "empty") {
    return "No rows returned";
  }

  if (state === "review_denied") {
    return "Review denied before run creation";
  }

  if (state === "execution_denied") {
    return "Execution denied";
  }

  if (state === "failed") {
    return "Execution failed";
  }

  if (state === "canceled") {
    return "Execution canceled";
  }

  return "Results placeholder";
}

function renderResultContent(state: CanonicalWorkflowState) {
  if (state === "completed") {
    return (
      <div className="result-table" role="table" aria-label="Placeholder query results">
        <div className="result-row result-row-head" role="row">
          <span role="columnheader">Vendor</span>
          <span role="columnheader">Quarterly spend</span>
          <span role="columnheader">Guard note</span>
        </div>
        <div className="result-row" role="row">
          <span role="cell">Northwind Health</span>
          <span role="cell">$842,000</span>
          <span role="cell">Within reviewed ceiling</span>
        </div>
        <div className="result-row" role="row">
          <span role="cell">Harbor Transit</span>
          <span role="cell">$611,000</span>
          <span role="cell">Approved dataset projection</span>
        </div>
        <div className="result-row" role="row">
          <span role="cell">Blue Summit Labs</span>
          <span role="cell">$488,000</span>
          <span role="cell">Placeholder rows only</span>
        </div>
      </div>
    );
  }

  if (state === "review_denied") {
    return (
      <div className="state-callout state-callout-danger">
        <p className="state-callout-title">Review denied state reached</p>
        <p>
          The request stopped before execution. Candidate review context remains visible so the
          operator can revise without inventing a run record.
        </p>
      </div>
    );
  }

  if (state === "empty") {
    return (
      <div className="state-callout state-callout-empty">
        <p className="state-callout-title">Empty state reached</p>
        <p>
          The approved workflow returned zero rows. Keep the question, SQL preview, and guard
          history intact so the operator can revise without losing context.
        </p>
      </div>
    );
  }

  if (state === "execution_denied") {
    return (
      <div className="state-callout state-callout-danger">
        <p className="state-callout-title">Execution denied state reached</p>
        <p>
          The shell preserves the denied run record and keeps execution closed instead of implying
          that an earlier preview automatically became successful output.
        </p>
      </div>
    );
  }

  if (state === "failed") {
    return (
      <div className="state-callout state-callout-danger">
        <p className="state-callout-title">Failed state reached</p>
        <p>
          A run was created, but it ended in failure. The operator sees the run anchor and failure
          posture instead of placeholder rows.
        </p>
      </div>
    );
  }

  if (state === "canceled") {
    return (
      <div className="state-callout">
        <p className="state-callout-title">Canceled state reached</p>
        <p>
          Cancellation keeps the run history visible and distinct from empty, denied, or failed
          outcomes.
        </p>
      </div>
    );
  }

  return (
    <div className="placeholder-block">
      <p className="placeholder-title">Result preview pending</p>
      <p>
        Submit the question to move into SQL review. Result placeholders stay separate from SQL
        and guard context even before execution wiring exists.
      </p>
    </div>
  );
}

function renderStatePanel(state: CanonicalWorkflowState, question: string) {
  if (state === "signin") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Authentication placeholder</p>
        <h2>Sign in state</h2>
        <p className="section-copy">
          This issue stops at the custom shell. The sign-in card is visible and reachable, but it
          does not establish a real identity session yet.
        </p>
        <div className="signin-actions">
          <a className="action-link" href={buildStateHref("query", question)}>
            Continue to query input
          </a>
          <span className="inline-note">Real auth wiring stays out of scope.</span>
        </div>
      </div>
    );
  }

  if (state === "preview") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Review mode</p>
        <h2>SQL preview state</h2>
        <p className="section-copy">
          Query submission lands here first so generated SQL and guard posture can be reviewed
          before any future execution path is introduced.
        </p>
        <div className="action-row">
          <a className="action-link" href={buildStateHref("completed", question)}>
            Open completed state
          </a>
          <a className="ghost-link" href={buildStateHref("empty", question)}>
            Open empty state
          </a>
        </div>
      </div>
    );
  }

  if (state === "completed") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Inspection mode</p>
        <h2>Completed state</h2>
        <p className="section-copy">
          Execution-backed rows stay separate from preview and guard surfaces so completed output
          is anchored to a specific run instead of a generic result placeholder.
        </p>
        <div className="action-row">
          <a className="action-link" href={buildStateHref("empty", question)}>
            Open empty state
          </a>
          <a className="ghost-link" href={buildStateHref("failed", question)}>
            Open failed state
          </a>
        </div>
      </div>
    );
  }

  if (state === "empty") {
    return (
      <div className="state-hero">
        <p className="eyebrow">No-data path</p>
        <h2>Empty state</h2>
        <p className="section-copy">
          Empty outcomes are modeled explicitly so the operator can distinguish no-data from
          denial, auth failure, or transport issues.
        </p>
        <div className="action-row">
          <a className="action-link" href={buildStateHref("query", question)}>
            Revise question
          </a>
          <a className="ghost-link" href={buildStateHref("preview", question)}>
            Back to SQL preview
          </a>
        </div>
      </div>
    );
  }

  if (state === "review_denied") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Pre-execution block</p>
        <h2>Review denied state</h2>
        <p className="section-copy">
          Pre-execution review failures stay attached to the candidate review surface. The operator
          sees a blocked candidate, not a synthetic run outcome.
        </p>
        <div className="action-row">
          <a className="action-link" href={buildStateHref("query", question)}>
            Return to query input
          </a>
          <a className="ghost-link" href={buildStateHref("preview", question)}>
            Back to SQL preview
          </a>
        </div>
      </div>
    );
  }

  if (state === "execution_denied") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Run denied</p>
        <h2>Execution denied state</h2>
        <p className="section-copy">
          Execute-time denial is distinct from review denial. The shell keeps the operator on the
          run-backed outcome that was rejected after preview.
        </p>
        <div className="action-row">
          <a className="action-link" href={buildStateHref("preview", question)}>
            Back to SQL preview
          </a>
          <a className="ghost-link" href={buildStateHref("query", question)}>
            Revise question
          </a>
        </div>
      </div>
    );
  }

  if (state === "failed") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Run failure</p>
        <h2>Failed state</h2>
        <p className="section-copy">
          Failure after execution start keeps the run identity, source binding, and reviewed
          candidate visible for operator diagnosis.
        </p>
        <div className="action-row">
          <a className="action-link" href={buildStateHref("completed", question)}>
            Open completed state
          </a>
          <a className="ghost-link" href={buildStateHref("query", question)}>
            Revise question
          </a>
        </div>
      </div>
    );
  }

  if (state === "canceled") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Run canceled</p>
        <h2>Canceled state</h2>
        <p className="section-copy">
          Cancellation is presented as its own terminal outcome so operators do not confuse
          interrupted work with denial, failure, or an empty result.
        </p>
        <div className="action-row">
          <a className="action-link" href={buildStateHref("query", question)}>
            Start a new draft
          </a>
          <a className="ghost-link" href={buildStateHref("completed", question)}>
            Compare completed state
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="state-hero">
      <p className="eyebrow">Compose</p>
      <h2>Query input state</h2>
      <p className="section-copy">
        The custom shell is now SafeQuery-owned. Question input, SQL preview, guard status, and
        results are separated into stable surfaces before real execution wiring is added.
      </p>
    </div>
  );
}

export function QueryWorkflowShell({
  apiUrl,
  health,
  question,
  state
}: QueryWorkflowShellProps) {
  const normalizedState = resolveWorkflowState(state);
  const sqlPreview = getSqlPreview(question);
  const activeState = workflowStates[normalizedState];
  const queryLocked = normalizedState === "signin";
  const guardTone = getGuardTone(normalizedState);
  const workflowContext = getWorkflowContext(normalizedState);

  return (
    <main className="app-shell">
      <header className="frame-shell">
        <div className="frame-intro">
          <div>
            <p className="eyebrow">SafeQuery</p>
            <h1>Query workflow</h1>
          </div>
          <p className="frame-copy">
            A governed application shell for review-first NL2SQL work. This first pass stays
            independent from Vanna UI surfaces and keeps auth and execution as placeholders.
          </p>
        </div>

        <div className="frame-meta" aria-label="Application status">
          <div className="meta-card">
            <span className="meta-label">Current state</span>
            <strong>{activeState.label}</strong>
            <span className="meta-copy">{activeState.description}</span>
          </div>
          <HealthStatusCard apiUrl={apiUrl} initialHealth={health} />
          <div className="meta-card">
            <span className="meta-label">Boundary mode</span>
            <strong>Fail closed</strong>
            <span className="meta-copy">No auth or execution trust is inferred from placeholders.</span>
          </div>
        </div>

        <nav aria-label="Workflow states" className="state-nav">
          {workflowStateOrder.map((workflowState) => (
            <a
              aria-current={workflowState === normalizedState ? "page" : undefined}
              className="state-nav-link"
              href={buildStateHref(workflowState, question)}
              key={workflowState}
            >
              {workflowStates[workflowState].label}
            </a>
          ))}
        </nav>
      </header>

      <section className="workspace-grid">
        <div className="primary-column">
          <section className="surface surface-primary">
            {renderStatePanel(normalizedState, question)}
          </section>

          <section className="surface surface-primary">
            <div className="section-header">
              <div>
                <p className="eyebrow">Question input</p>
                <h2 className="panel-title">Compose the analyst question</h2>
              </div>
              <span className={`surface-badge surface-badge-${queryLocked ? "muted" : "active"}`}>
                {queryLocked ? "Read only" : "Ready"}
              </span>
            </div>

            <form action="/" className="query-form" method="get">
              <input name="state" type="hidden" value="preview" />
              <label className="field-label" htmlFor="question">
                Natural-language question
              </label>
              <textarea
                defaultValue={question}
                disabled={queryLocked}
                id="question"
                name="question"
                placeholder="Ask a governed business question."
                rows={6}
              />
              <div className="form-actions">
                <button disabled={queryLocked} type="submit">
                  Generate preview
                </button>
                <a className="ghost-link" href={buildStateHref("completed", question)}>
                  Open completed state
                </a>
              </div>
            </form>
          </section>
        </div>

        <aside className="support-column">
          <section className="surface surface-secondary">
            <div className="section-header">
              <div>
                <p className="eyebrow">Generated SQL</p>
                <h2 className="panel-title">SQL preview placeholder</h2>
              </div>
              <span className="surface-badge surface-badge-code">Preview</span>
            </div>
            <pre className="sql-preview">
              <code>{sqlPreview}</code>
            </pre>
          </section>

          <section className="surface surface-secondary">
            <div className="section-header">
              <div>
                <p className="eyebrow">Workflow anchors</p>
                <h2 className="panel-title">Source and lifecycle context</h2>
              </div>
              <span className="surface-badge surface-badge-code">Bound context</span>
            </div>
            <div className="guard-list">
              <div className="guard-item">
                <span className="meta-label">Source identity</span>
                <strong>{workflowContext.sourceIdentity}</strong>
              </div>
              <div className="guard-item">
                <span className="meta-label">
                  {workflowContext.requestIdentity ? "Request identity" : "Request posture"}
                </span>
                <strong>{workflowContext.requestIdentity ?? "Draft only"}</strong>
              </div>
              <div className="guard-item">
                <span className="meta-label">
                  {workflowContext.candidateIdentity ? "Candidate identity" : "Draft posture"}
                </span>
                <strong>{workflowContext.candidateIdentity ?? "Draft only"}</strong>
              </div>
              <div className="guard-item">
                <span className="meta-label">
                  {workflowContext.candidateState ? "Candidate state" : "Lifecycle state"}
                </span>
                <strong>{workflowContext.candidateState ?? "drafting"}</strong>
              </div>
              {workflowContext.runIdentity ? (
                <>
                  <div className="guard-item">
                    <span className="meta-label">Run identity</span>
                    <strong>{workflowContext.runIdentity}</strong>
                  </div>
                  <div className="guard-item">
                    <span className="meta-label">Run state</span>
                    <strong>{workflowContext.runState}</strong>
                  </div>
                </>
              ) : null}
              <div className="guard-item">
                <span className="meta-label">
                  {workflowContext.lifecycleTimestamp ? "Lifecycle timestamp" : "Lifecycle posture"}
                </span>
                <strong>{workflowContext.lifecycleTimestamp ?? "No submitted record yet"}</strong>
              </div>
            </div>
          </section>

          <section className="surface surface-secondary">
            <div className="section-header">
              <div>
                <p className="eyebrow">Guard status</p>
                <h2 className="panel-title">{getGuardHeadline(normalizedState)}</h2>
              </div>
              <span className={`surface-badge surface-badge-${guardTone}`}>{guardTone}</span>
            </div>
            <p className="section-copy">{getGuardCopy(normalizedState)}</p>
            <div className="guard-list">
              <div className="guard-item">
                <span className="meta-label">Auth</span>
                <strong>Placeholder only</strong>
              </div>
              <div className="guard-item">
                <span className="meta-label">Approval record</span>
                <strong>Not yet wired</strong>
              </div>
              <div className="guard-item">
                <span className="meta-label">Execution path</span>
                <strong>Blocked in this issue</strong>
              </div>
            </div>
          </section>

          <section className="surface surface-secondary">
            <div className="section-header">
              <div>
                <p className="eyebrow">Results</p>
                <h2 className="panel-title">{getResultTitle(normalizedState)}</h2>
              </div>
              <a className="inline-link" href={`${apiUrl}/health`} rel="noreferrer" target="_blank">
                API health
              </a>
            </div>
            {renderResultContent(normalizedState)}
          </section>
        </aside>
      </section>
    </main>
  );
}
