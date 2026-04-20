import { HealthStatusCard } from "./health-status-card";
import type { HealthSnapshot } from "../lib/health";

type WorkflowState = "signin" | "query" | "preview" | "results" | "empty" | "error";

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

const workflowStates: Record<WorkflowState, StateDefinition> = {
  empty: {
    description: "The workflow completed, but the approved query returned no rows.",
    label: "Empty state"
  },
  error: {
    description: "The workflow hit a guarded failure path and is holding execution closed.",
    label: "Error state"
  },
  preview: {
    description: "The question has been staged for analyst review with generated SQL still in placeholder mode.",
    label: "SQL preview"
  },
  query: {
    description: "Compose a governed question and move into review without leaving the product shell.",
    label: "Query input"
  },
  results: {
    description: "Previewed SQL has advanced to a placeholder result view for future execution wiring.",
    label: "Result state"
  },
  signin: {
    description: "Reserved sign-in entrypoint before any real authentication bridge is wired.",
    label: "Sign in"
  }
};

export function resolveWorkflowState(value?: string): WorkflowState {
  if (value && Object.prototype.hasOwnProperty.call(workflowStates, value)) {
    return value as WorkflowState;
  }

  return "query";
}

function buildStateHref(state: WorkflowState, question: string): string {
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

function getGuardTone(state: WorkflowState): string {
  if (state === "error") {
    return "danger";
  }

  if (state === "results" || state === "empty") {
    return "success";
  }

  return "warning";
}

function getGuardHeadline(state: WorkflowState): string {
  if (state === "error") {
    return "Blocked pending trusted prerequisite";
  }

  if (state === "results") {
    return "Preview approved for placeholder execution";
  }

  if (state === "empty") {
    return "Execution completed with no approved rows";
  }

  return "Awaiting analyst review";
}

function getGuardCopy(state: WorkflowState): string {
  if (state === "error") {
    return "No auth context, approval record, or execution binding is inferred here. The shell stays fail-closed and surfaces a review-needed error placeholder instead.";
  }

  if (state === "results") {
    return "Guard status remains explicit even in placeholder mode so the workflow keeps query intent, SQL review, and result inspection separate.";
  }

  if (state === "empty") {
    return "The result surface can represent a clean no-data outcome without restyling the rest of the page or hiding guard context.";
  }

  return "The first shell stops at review boundaries. No real auth, SQL generation, or execution path is trusted in this issue.";
}

function getResultTitle(state: WorkflowState): string {
  if (state === "results") {
    return "Placeholder result set";
  }

  if (state === "empty") {
    return "No rows returned";
  }

  if (state === "error") {
    return "Execution unavailable";
  }

  return "Results placeholder";
}

function renderResultContent(state: WorkflowState) {
  if (state === "results") {
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

  if (state === "error") {
    return (
      <div className="state-callout state-callout-danger">
        <p className="state-callout-title">Error state reached</p>
        <p>
          The shell presents a controlled failure placeholder instead of implying that an
          unauthorized execution succeeded.
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

function renderStatePanel(state: WorkflowState, question: string) {
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
          <a className="action-link" href={buildStateHref("results", question)}>
            Open result placeholder
          </a>
          <a className="ghost-link" href={buildStateHref("empty", question)}>
            Open empty state
          </a>
        </div>
      </div>
    );
  }

  if (state === "results") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Inspection mode</p>
        <h2>Result state</h2>
        <p className="section-copy">
          Placeholder rows confirm the layout contract for reviewed output without pretending that
          SafeQuery already executes approved SQL.
        </p>
        <div className="action-row">
          <a className="action-link" href={buildStateHref("empty", question)}>
            Open empty state
          </a>
          <a className="ghost-link" href={buildStateHref("error", question)}>
            Open error state
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

  if (state === "error") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Guarded failure path</p>
        <h2>Error state</h2>
        <p className="section-copy">
          Fail-closed placeholders keep boundary signals explicit. Missing trusted prerequisites do
          not silently degrade into success or partial results.
        </p>
        <div className="action-row">
          <a className="action-link" href={buildStateHref("query", question)}>
            Return to query input
          </a>
          <a className="ghost-link" href={buildStateHref("signin", question)}>
            Open sign in
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
  const sqlPreview = getSqlPreview(question);
  const activeState = workflowStates[state];
  const queryLocked = state === "signin";
  const guardTone = getGuardTone(state);

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
          {(Object.keys(workflowStates) as WorkflowState[]).map((workflowState) => (
            <a
              aria-current={workflowState === state ? "page" : undefined}
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
          <section className="surface surface-primary">{renderStatePanel(state, question)}</section>

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
                <a className="ghost-link" href={buildStateHref("results", question)}>
                  Open result state
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
                <p className="eyebrow">Guard status</p>
                <h2 className="panel-title">{getGuardHeadline(state)}</h2>
              </div>
              <span className={`surface-badge surface-badge-${guardTone}`}>{guardTone}</span>
            </div>
            <p className="section-copy">{getGuardCopy(state)}</p>
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
                <h2 className="panel-title">{getResultTitle(state)}</h2>
              </div>
              <a className="inline-link" href={`${apiUrl}/health`} rel="noreferrer" target="_blank">
                API health
              </a>
            </div>
            {renderResultContent(state)}
          </section>
        </aside>
      </section>
    </main>
  );
}
