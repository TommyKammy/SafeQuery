"use client";

import { type FormEvent, useEffect, useState } from "react";
import { HealthStatusCard } from "./health-status-card";
import type { HealthSnapshot } from "../lib/health";
import type {
  OperatorHistoryItem,
  OperatorWorkflowSnapshot,
  SourceOption
} from "../lib/operator-workflow";

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
  historyRecordId?: string;
  operatorWorkflow: OperatorWorkflowSnapshot;
  question: string;
  sourceId?: string;
  state: WorkflowState;
};

type StateDefinition = {
  description: string;
  label: string;
};

type WorkflowContext = {
  candidateIdentity?: string;
  candidateState?: string;
  guardStatus?: string;
  lifecycleTimestamp?: string;
  requestIdentity?: string;
  runIdentity?: string;
  runState?: string | null;
  sourceIdentity: string;
};

type ResolvedSourceBinding = {
  blockedReason?: string;
  source?: SourceOption;
  state: CanonicalWorkflowState;
};

type WorkflowHrefContext = {
  historyItemType?: OperatorHistoryItem["itemType"];
  historyRecordId?: string;
};

type PreviewSubmissionStatus =
  | {
      status: "idle";
    }
  | {
      status: "submitting";
    }
  | {
      code: string;
      message: string;
      status: "failed";
    }
  | {
      candidateState: string;
      requestState: string;
      sourceId: string;
      status: "denied" | "pending";
    }
  | {
      code: string;
      message: string;
      status: "malformed" | "unavailable";
    }
  | {
      candidateState: string;
      requestState: string;
      sourceId: string;
      status: "succeeded";
    };

type PreviewSubmissionResult = {
  candidateId: string;
  candidateSql: string | null;
  candidateState: string;
  guardStatus: string;
  requestId: string;
  requestState: string;
  sourceId: string;
};

type AuthoritativeCandidatePreview = {
  candidateId: string;
  candidateSql: string | null;
  candidateState: string;
  guardStatus: string;
  requestId?: string;
  sourceId: string;
  sourceLabel?: string;
};

type AuthoritativeRunContext = {
  lifecycleState: string;
  lifecycleTimestamp: string;
  primaryDenyCode?: string | null;
  resultTruncated?: boolean | null;
  rowCount?: number | null;
  runIdentity: string;
  runState?: string | null;
  sourceLabel: string;
};

type ApiErrorEnvelope = {
  code: string;
  message: string;
};

const workflowStates: Record<CanonicalWorkflowState, StateDefinition> = {
  canceled: {
    description: "Execution started from a reviewed candidate but stopped before the run completed.",
    label: "Canceled"
  },
  completed: {
    description:
      "Execution completed for a reviewed run record; rows appear only when authoritative results are attached.",
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
    description: "The operator request has been staged for governed candidate review.",
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

function findSourceOption(
  sourceOptions: SourceOption[],
  sourceId?: string
): SourceOption | undefined {
  return sourceOptions.find((source) => source.sourceId === sourceId);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readRequiredString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value : undefined;
}

function readCsrfToken(): string | undefined {
  const token =
    document.querySelector<HTMLMetaElement>('meta[name="safequery-csrf-token"]')?.content ??
    document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content ??
    document.querySelector<HTMLInputElement>('input[name="csrf_token"]')?.value;

  return readRequiredString(token);
}

function parseApiErrorEnvelope(value: unknown): ApiErrorEnvelope | null {
  if (!isObject(value) || !isObject(value.error)) {
    return null;
  }

  const code = readRequiredString(value.error.code);
  const message = readRequiredString(value.error.message);
  if (!code || !message) {
    return null;
  }

  return { code, message };
}

function previewSubmissionStatusForApiError(
  error: ApiErrorEnvelope | null
): PreviewSubmissionStatus {
  if (error?.code === "preview_source_malformed") {
    return {
      code: error.code,
      message: error.message,
      status: "malformed"
    };
  }

  if (error?.code === "preview_source_unavailable") {
    return {
      code: error.code,
      message: error.message,
      status: "unavailable"
    };
  }

  return {
    code: error?.code ?? "preview_submission_failed",
    message:
      error?.message ?? "Preview submission failed before an authoritative candidate was returned.",
    status: "failed"
  };
}

function parsePreviewSubmissionResult(
  value: unknown,
  expectedSourceId: string
): PreviewSubmissionResult | null {
  if (!isObject(value) || !isObject(value.request) || !isObject(value.candidate)) {
    return null;
  }

  const requestSourceId = readRequiredString(value.request.source_id);
  const requestId = readRequiredString(value.request.request_id);
  const candidateSourceId = readRequiredString(value.candidate.source_id);
  const candidateId = readRequiredString(value.candidate.candidate_id);
  const candidateSql =
    typeof value.candidate.candidate_sql === "string" &&
    value.candidate.candidate_sql.trim().length > 0
      ? value.candidate.candidate_sql
      : null;
  const guardStatus = readRequiredString(value.candidate.guard_status);
  const requestState = readRequiredString(value.request.state);
  const candidateState = readRequiredString(value.candidate.state);

  if (
    !requestId ||
    requestSourceId !== expectedSourceId ||
    !candidateId ||
    candidateSourceId !== expectedSourceId ||
    !guardStatus ||
    !requestState ||
    !candidateState
  ) {
    return null;
  }

  return {
    candidateId,
    candidateSql,
    candidateState,
    guardStatus,
    requestId,
    requestState,
    sourceId: expectedSourceId
  };
}

function isPendingPreviewState(result: PreviewSubmissionResult): boolean {
  const requestState = result.requestState.toLowerCase();
  const candidateState = result.candidateState.toLowerCase();

  return (
    requestState === "pending" ||
    requestState === "submitted" ||
    candidateState === "pending" ||
    candidateState === "pending_generation"
  );
}

function isDeniedPreviewState(result: PreviewSubmissionResult): boolean {
  const requestState = result.requestState.toLowerCase();
  const candidateState = result.candidateState.toLowerCase();

  return (
    requestState === "blocked" ||
    requestState === "review_denied" ||
    requestState === "preview_denied" ||
    candidateState === "blocked" ||
    candidateState === "denied" ||
    candidateState === "invalidated" ||
    candidateState === "review_denied"
  );
}

function isReadyPreviewState(result: PreviewSubmissionResult): boolean {
  return result.candidateState.toLowerCase() === "preview_ready";
}

function resolveSourceBinding(
  sourceOptions: SourceOption[],
  state: CanonicalWorkflowState,
  sourceId?: string
): ResolvedSourceBinding {
  const source = findSourceOption(sourceOptions, sourceId);

  if (state === "signin") {
    return {
      source,
      state
    };
  }

  if (state === "query") {
    if (sourceOptions.length === 0) {
      return {
        blockedReason: "Live source registry data is unavailable, so preview submission remains blocked.",
        state: "query"
      };
    }

    if (sourceId && source?.activationPosture !== "active") {
      return {
        blockedReason: "Select an executable source before preview can be requested.",
        state: "query"
      };
    }

    return {
      source,
      state
    };
  }

  if (!sourceId || source === undefined) {
    return {
      blockedReason: "Select an executable source before preview can be requested.",
      state: "query"
    };
  }

  if (source.activationPosture !== "active") {
    return {
      blockedReason: "The selected source is not executable for preview submission.",
      state: "query"
    };
  }

  return {
    source,
    state
  };
}

function renderHistoryItem(item: OperatorHistoryItem) {
  return (
    <a
      className="history-item"
      href={buildStateHref(historyItemToState(item), item.label, item.sourceId, {
        historyItemType: item.itemType,
        historyRecordId: item.recordId
      })}
      key={`${item.itemType}:${item.recordId}`}
    >
      <span className="history-type">{item.itemType}</span>
      <strong>{item.label}</strong>
      <span>{item.sourceLabel}</span>
      <span>{item.lifecycleState}</span>
    </a>
  );
}

function historyItemToState(item: OperatorHistoryItem): CanonicalWorkflowState {
  const lifecycleState = item.lifecycleState.toLowerCase();
  const runState = item.runState?.toLowerCase();
  const guardStatus = item.guardStatus?.toLowerCase();

  if (item.itemType === "request" || item.itemType === "candidate") {
    if (
      lifecycleState === "review_denied" ||
      lifecycleState === "blocked" ||
      lifecycleState === "invalidated" ||
      guardStatus === "blocked" ||
      guardStatus === "invalidated"
    ) {
      return "review_denied";
    }

    return "preview";
  }

  if (runState === "completed" || lifecycleState === "completed") {
    return "completed";
  }

  if (runState === "empty" || lifecycleState === "empty") {
    return "empty";
  }

  if (runState === "execution_denied" || lifecycleState === "execution_denied") {
    return "execution_denied";
  }

  if (runState === "failed" || lifecycleState === "failed") {
    return "failed";
  }

  if (runState === "canceled" || lifecycleState === "canceled") {
    return "canceled";
  }

  return "preview";
}

function getWorkflowDataStatusCopy(status: OperatorWorkflowSnapshot["status"]): string {
  if (status === "live") {
    return "Source registry and history summary loaded from the backend workflow contract.";
  }

  if (status === "unauthenticated") {
    return "Sign in before loading the operator workflow. No source or history data is trusted yet.";
  }

  if (status === "session_invalid") {
    return "The operator session is no longer valid. Sign in again before continuing.";
  }

  if (status === "csrf_failed") {
    return "The request freshness check failed. Refresh the page before continuing.";
  }

  if (status === "entitlement_denied") {
    return "The signed-in operator is not entitled to this source or workflow context.";
  }

  if (status === "malformed") {
    return "Backend workflow payload was malformed, so the source selector remains blocked.";
  }

  return "Backend workflow payload is unavailable, so the source selector remains blocked.";
}

function buildStateHref(
  state: CanonicalWorkflowState,
  question: string,
  sourceId?: string,
  context?: WorkflowHrefContext
): string {
  const params = new URLSearchParams({
    question,
    state
  });

  if (sourceId) {
    params.set("source_id", sourceId);
  }

  if (context?.historyItemType && context.historyRecordId) {
    params.set("history_item_type", context.historyItemType);
    params.set("history_record_id", context.historyRecordId);
  }

  return `/?${params.toString()}`;
}

function findAuthoritativeCandidatePreview(
  history: OperatorHistoryItem[],
  sourceId?: string,
  historyRecordId?: string
): AuthoritativeCandidatePreview | null {
  const candidate = history.find((item) => {
    if (item.itemType !== "candidate") {
      return false;
    }

    if (historyRecordId) {
      return item.recordId === historyRecordId;
    }

    return !sourceId || item.sourceId === sourceId;
  });
  if (!candidate) {
    return null;
  }

  return {
    candidateId: candidate.recordId,
    candidateSql: candidate.candidateSql ?? null,
    candidateState: candidate.lifecycleState,
    guardStatus: candidate.guardStatus ?? "pending",
    requestId: candidate.requestId ?? undefined,
    sourceId: candidate.sourceId,
    sourceLabel: candidate.sourceLabel
  };
}

function findAuthoritativeRunContext(
  history: OperatorHistoryItem[],
  sourceId?: string,
  historyRecordId?: string
): AuthoritativeRunContext | null {
  if (!sourceId || !historyRecordId) {
    return null;
  }

  const run = history.find(
    (item) =>
      item.itemType === "run" &&
      item.sourceId === sourceId &&
      item.recordId === historyRecordId
  );

  if (!run) {
    return null;
  }

  return {
    lifecycleState: run.lifecycleState,
    lifecycleTimestamp: run.occurredAt,
    primaryDenyCode: run.primaryDenyCode,
    resultTruncated: run.resultTruncated,
    rowCount: run.rowCount,
    runIdentity: run.recordId,
    runState: run.runState,
    sourceLabel: run.sourceLabel
  };
}

function renderCandidateSqlPreview(preview: AuthoritativeCandidatePreview | null) {
  if (!preview) {
    return (
      <div className="placeholder-block">
        <p className="placeholder-title">No authoritative candidate selected</p>
        <p>
          Submit the question for preview or reopen a candidate history row before SQL preview can
          be shown.
        </p>
      </div>
    );
  }

  if (!preview.candidateSql) {
    return (
      <div className="placeholder-block">
        <p className="placeholder-title">Canonical SQL pending</p>
        <p>Canonical SQL has not been generated for this candidate.</p>
      </div>
    );
  }

  return (
    <pre className="sql-preview">
      <code>{preview.candidateSql}</code>
    </pre>
  );
}

function getWorkflowContext(
  state: CanonicalWorkflowState,
  source?: SourceOption,
  candidatePreview?: AuthoritativeCandidatePreview | null,
  runContext?: AuthoritativeRunContext | null
): WorkflowContext {
  const sourceIdentity =
    candidatePreview?.sourceLabel ??
    runContext?.sourceLabel ??
    source?.displayLabel ??
    "No source selected yet";

  if (candidatePreview && (state === "preview" || state === "review_denied")) {
    return {
      candidateIdentity: candidatePreview.candidateId,
      candidateState: candidatePreview.candidateState,
      guardStatus: candidatePreview.guardStatus,
      requestIdentity: candidatePreview.requestId,
      sourceIdentity
    };
  }

  if (state === "preview" || state === "review_denied") {
    return {
      sourceIdentity
    };
  }

  if (
    runContext &&
    (state === "completed" ||
      state === "empty" ||
      state === "execution_denied" ||
      state === "failed" ||
      state === "canceled")
  ) {
    return {
      lifecycleTimestamp: runContext.lifecycleTimestamp,
      runIdentity: runContext.runIdentity,
      runState: runContext.runState ?? runContext.lifecycleState,
      sourceIdentity
    };
  }

  if (state === "query" || state === "signin") {
    return {
      sourceIdentity
    };
  }

  return {
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
    return "Execution completed";
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

  return "Awaiting operator review";
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

  return "The shell stops at review boundaries unless an authoritative candidate record supplies guard posture and SQL preview data.";
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

  return "Results unavailable";
}

function renderResultContent(
  state: CanonicalWorkflowState,
  runContext?: AuthoritativeRunContext | null
) {
  if (state === "completed") {
    if (
      runContext &&
      runContext.rowCount !== null &&
      runContext.rowCount !== undefined &&
      runContext.resultTruncated !== null &&
      runContext.resultTruncated !== undefined
    ) {
      return (
        <div className="state-callout state-callout-success">
          <p className="state-callout-title">Authoritative result metadata</p>
          <p>
            {runContext.rowCount} rows returned; result payload{" "}
            {runContext.resultTruncated ? "truncated" : "not truncated"}.
          </p>
        </div>
      );
    }

    return (
      <div className="state-callout state-callout-empty">
        <p className="state-callout-title">Execution results unavailable</p>
        <p>
          No backend result rows are attached to this shell view. SafeQuery withholds the table
          until an authoritative execution payload is returned for the selected run.
        </p>
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
        {runContext?.primaryDenyCode ? <p>Deny code: {runContext.primaryDenyCode}</p> : null}
      </div>
    );
  }

  if (state === "failed") {
    return (
      <div className="state-callout state-callout-danger">
        <p className="state-callout-title">Failed state reached</p>
        <p>
          A run was created, but it ended in failure. The operator sees the run anchor and failure
          posture instead of invented rows.
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
        Submit the question to move into SQL review. Results remain unavailable until execution
        returns authoritative rows.
      </p>
    </div>
  );
}

function renderStatePanel(
  state: CanonicalWorkflowState,
  question: string,
  sourceId?: string,
  canOpenCompleted = false,
  context?: WorkflowHrefContext
) {
  if (state === "signin") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Authentication required</p>
        <h2>Sign in state</h2>
        <p className="section-copy">
          This issue stops at the custom shell. The sign-in card is visible and reachable, but it
          does not establish a real identity session yet.
        </p>
        <div className="signin-actions">
          <a className="action-link" href={buildStateHref("query", question, sourceId)}>
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
        {canOpenCompleted ? (
          <div className="action-row">
            <a
              className="action-link"
              href={buildStateHref("completed", question, sourceId, context)}
            >
              Open completed state
            </a>
            <a className="ghost-link" href={buildStateHref("empty", question, sourceId, context)}>
              Open empty state
            </a>
          </div>
        ) : null}
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
          is anchored to a specific run instead of generic result content.
        </p>
        <div className="action-row">
          <a className="action-link" href={buildStateHref("empty", question, sourceId)}>
            Open empty state
          </a>
          <a className="ghost-link" href={buildStateHref("failed", question, sourceId)}>
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
          <a className="action-link" href={buildStateHref("query", question, sourceId)}>
            Revise question
          </a>
          <a className="ghost-link" href={buildStateHref("preview", question, sourceId)}>
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
          <a className="action-link" href={buildStateHref("query", question, sourceId)}>
            Return to query input
          </a>
          <a className="ghost-link" href={buildStateHref("preview", question, sourceId)}>
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
          <a className="action-link" href={buildStateHref("preview", question, sourceId)}>
            Back to SQL preview
          </a>
          <a className="ghost-link" href={buildStateHref("query", question, sourceId)}>
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
          <a className="action-link" href={buildStateHref("completed", question, sourceId)}>
            Open completed state
          </a>
          <a className="ghost-link" href={buildStateHref("query", question, sourceId)}>
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
          <a className="action-link" href={buildStateHref("query", question, sourceId)}>
            Start a new draft
          </a>
          <a className="ghost-link" href={buildStateHref("completed", question, sourceId)}>
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
  historyRecordId,
  operatorWorkflow,
  question,
  sourceId,
  state
}: QueryWorkflowShellProps) {
  const requestedState = resolveWorkflowState(state);
  const [previewSubmission, setPreviewSubmission] = useState<PreviewSubmissionStatus>({
    status: "idle"
  });
  const [submittedCandidatePreview, setSubmittedCandidatePreview] =
    useState<AuthoritativeCandidatePreview | null>(null);
  const [submittedQuestion, setSubmittedQuestion] = useState(question);
  const [submittedSourceId, setSubmittedSourceId] = useState(sourceId);
  const [submittedState, setSubmittedState] = useState(requestedState);

  useEffect(() => {
    setSubmittedQuestion(question);
    setSubmittedSourceId(sourceId);
    setSubmittedState(requestedState);
    setPreviewSubmission({ status: "idle" });
    setSubmittedCandidatePreview(null);
  }, [question, requestedState, sourceId]);

  const sourceBinding = resolveSourceBinding(
    operatorWorkflow.sources,
    submittedState,
    submittedSourceId
  );
  const normalizedState = sourceBinding.state;
  const activeState = workflowStates[normalizedState];
  const queryLocked = normalizedState === "signin" || previewSubmission.status === "submitting";
  const guardTone = getGuardTone(normalizedState);
  const historyCandidatePreview = findAuthoritativeCandidatePreview(
    operatorWorkflow.history,
    submittedSourceId,
    historyRecordId
  );
  const historyRunContext = findAuthoritativeRunContext(
    operatorWorkflow.history,
    submittedSourceId,
    historyRecordId
  );
  const candidatePreview = submittedCandidatePreview ?? historyCandidatePreview;
  const draftSource = findSourceOption(operatorWorkflow.sources, submittedSourceId);
  const historySourceMismatch =
    candidatePreview !== null &&
    submittedSourceId !== undefined &&
    candidatePreview.sourceId !== submittedSourceId;
  const workflowContext = getWorkflowContext(
    normalizedState,
    sourceBinding.source,
    candidatePreview,
    historyRunContext
  );
  const sourceSelectVisible = normalizedState === "query";
  const boundSourceId = sourceBinding.source?.sourceId;
  const candidateSourceId = candidatePreview?.sourceId ?? boundSourceId;
  const canOpenCompletedFromPreview =
    normalizedState === "preview" && candidatePreview !== null && !historySourceMismatch;
  const historyHrefContext =
    normalizedState === "preview" && historyRecordId && historyCandidatePreview
      ? {
          historyItemType: "candidate" as const,
          historyRecordId
        }
      : undefined;

  async function submitPreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (queryLocked) {
      return;
    }

    const formData = new FormData(event.currentTarget);
    const selectedSourceId = readRequiredString(formData.get("source_id"));
    const submittedQuestionText = readRequiredString(formData.get("question"));
    const selectedSource = findSourceOption(operatorWorkflow.sources, selectedSourceId);

    if (!selectedSourceId || !submittedQuestionText) {
      setPreviewSubmission({
        code: "invalid_request",
        message: "Select one executable source and enter a question before requesting preview.",
        status: "failed"
      });
      return;
    }

    if (!selectedSource || selectedSource.activationPosture !== "active") {
      setPreviewSubmission({
        code: "source_not_executable",
        message: "Select an executable source before preview can be requested.",
        status: "failed"
      });
      return;
    }

    setPreviewSubmission({ status: "submitting" });

    const headers: Record<string, string> = {
      "content-type": "application/json"
    };
    const csrfToken = readCsrfToken();
    if (csrfToken) {
      headers["x-safequery-csrf"] = csrfToken;
    }

    try {
      const response = await fetch(`${apiUrl}/requests/preview`, {
        body: JSON.stringify({
          question: submittedQuestionText,
          source_id: selectedSourceId
        }),
        credentials: "same-origin",
        headers,
        method: "POST"
      });
      let payload: unknown;
      try {
        payload = (await response.json()) as unknown;
      } catch {
        setPreviewSubmission({
          code: "preview_submission_unavailable",
          message: "Preview submission unavailable before an authoritative payload was returned.",
          status: "unavailable"
        });
        return;
      }

      if (!response.ok) {
        const error = parseApiErrorEnvelope(payload);
        setPreviewSubmission(previewSubmissionStatusForApiError(error));
        return;
      }

      const result = parsePreviewSubmissionResult(payload, selectedSourceId);
      if (!result) {
        setPreviewSubmission({
          code: "malformed_preview_response",
          message: "Preview response did not match the submitted source binding.",
          status: "malformed"
        });
        return;
      }

      if (isDeniedPreviewState(result)) {
        setSubmittedQuestion(submittedQuestionText);
        setSubmittedSourceId(result.sourceId);
        setSubmittedState("review_denied");
        setSubmittedCandidatePreview({
          candidateId: result.candidateId,
          candidateSql: result.candidateSql,
          candidateState: result.candidateState,
          guardStatus: result.guardStatus,
          requestId: result.requestId,
          sourceId: result.sourceId,
          sourceLabel: selectedSource.displayLabel
        });
        setPreviewSubmission({
          candidateState: result.candidateState,
          requestState: result.requestState,
          sourceId: result.sourceId,
          status: "denied"
        });
        return;
      }

      if (isPendingPreviewState(result) && !isReadyPreviewState(result)) {
        setSubmittedQuestion(submittedQuestionText);
        setSubmittedSourceId(result.sourceId);
        setSubmittedCandidatePreview({
          candidateId: result.candidateId,
          candidateSql: result.candidateSql,
          candidateState: result.candidateState,
          guardStatus: result.guardStatus,
          requestId: result.requestId,
          sourceId: result.sourceId,
          sourceLabel: selectedSource.displayLabel
        });
        setPreviewSubmission({
          candidateState: result.candidateState,
          requestState: result.requestState,
          sourceId: result.sourceId,
          status: "pending"
        });
        return;
      }

      if (!isReadyPreviewState(result)) {
        setPreviewSubmission({
          code: "malformed_preview_response",
          message: "Preview response returned an unrecognized authoritative lifecycle state.",
          status: "malformed"
        });
        return;
      }

      setSubmittedQuestion(submittedQuestionText);
      setSubmittedSourceId(result.sourceId);
      setSubmittedState("preview");
      setSubmittedCandidatePreview({
        candidateId: result.candidateId,
        candidateSql: result.candidateSql,
        candidateState: result.candidateState,
        guardStatus: result.guardStatus,
        requestId: result.requestId,
        sourceId: result.sourceId,
        sourceLabel: selectedSource.displayLabel
      });
      setPreviewSubmission({
        candidateState: result.candidateState,
        requestState: result.requestState,
        sourceId: result.sourceId,
        status: "succeeded"
      });
    } catch {
      setPreviewSubmission({
        code: "preview_submission_unavailable",
        message: "Preview submission transport is unavailable.",
        status: "unavailable"
      });
    }
  }

  return (
    <main className="app-shell">
      <header className="frame-shell">
        <div className="frame-intro">
          <div>
            <p className="eyebrow">SafeQuery</p>
            <h1>Query workflow</h1>
          </div>
          <p className="frame-copy">
            Operator shell for governed question review, SQL preview, and execution posture.
            Analyst-style extensions stay optional and outside the core shell.
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
            <span className="meta-copy">
              No auth or execution trust is inferred from unavailable data.
            </span>
          </div>
        </div>

        <nav aria-label="Workflow states" className="state-nav">
          {workflowStateOrder.map((workflowState) => (
            <a
              aria-current={workflowState === normalizedState ? "page" : undefined}
              className="state-nav-link"
              href={buildStateHref(workflowState, question, boundSourceId)}
              key={workflowState}
            >
              {workflowStates[workflowState].label}
            </a>
          ))}
        </nav>
      </header>

      <section className="workspace-grid">
        <aside className="history-column" aria-label="Operator history">
          <section className="surface surface-secondary">
            <div className="section-header">
              <div>
                <p className="eyebrow">History</p>
                <h2 className="panel-title">Source-aware workflow history</h2>
              </div>
              <span
                className={`surface-badge surface-badge-${
                  operatorWorkflow.status === "live" ? "active" : "danger"
                }`}
              >
                {operatorWorkflow.status}
              </span>
            </div>
            <p className="section-copy">{getWorkflowDataStatusCopy(operatorWorkflow.status)}</p>
            {operatorWorkflow.error ? (
              <div className="state-callout state-callout-danger">
                <p className="state-callout-title">{operatorWorkflow.error.code}</p>
                <p>{operatorWorkflow.error.message}</p>
              </div>
            ) : null}
            <div className="history-list">
              {operatorWorkflow.history.length > 0 ? (
                operatorWorkflow.history.map(renderHistoryItem)
              ) : (
                <div className="placeholder-block">
                  <p className="placeholder-title">No live history rows</p>
                  <p>
                    The shell keeps history empty until the backend returns authoritative request,
                    candidate, or run summaries.
                  </p>
                </div>
              )}
            </div>
          </section>
        </aside>
        <div className="primary-column">
          <section className="surface surface-primary">
            {renderStatePanel(
              normalizedState,
              question,
              candidateSourceId,
              canOpenCompletedFromPreview,
              historyHrefContext
            )}
          </section>

          <section className="surface surface-primary">
            <div className="section-header">
              <div>
                <p className="eyebrow">Question input</p>
                <h2 className="panel-title">Compose the operator request</h2>
              </div>
              <span className={`surface-badge surface-badge-${queryLocked ? "muted" : "active"}`}>
                {queryLocked ? "Read only" : "Ready"}
              </span>
            </div>

            <form className="query-form" onSubmit={submitPreview}>
              {sourceSelectVisible ? (
                <>
                  <label className="field-label" htmlFor="source_id">
                    Source
                  </label>
                  <select
                    defaultValue={boundSourceId ?? ""}
                    disabled={queryLocked}
                    id="source_id"
                    name="source_id"
                    required
                  >
                    <option value="">Select one source</option>
                    {operatorWorkflow.sources.map((source) => (
                      <option
                        disabled={source.activationPosture !== "active"}
                        key={source.sourceId}
                        value={source.sourceId}
                      >
                        {source.displayLabel}
                        {source.activationPosture === "active" ? "" : " (Unavailable for preview)"}
                      </option>
                    ))}
                  </select>
                  <p className="section-copy">
                    Choose one explicit source before preview submission. SafeQuery does not infer or
                    auto-route the initial source binding.
                  </p>
                  {sourceBinding.blockedReason ? (
                    <div className="state-callout state-callout-danger">
                      <p className="state-callout-title">Preview submission blocked</p>
                      <p>{sourceBinding.blockedReason}</p>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="guard-list">
                  <div className="guard-item">
                    <span className="meta-label">Bound source</span>
                    <strong>{workflowContext.sourceIdentity}</strong>
                  </div>
                  <div className="guard-item">
                    <span className="meta-label">Source posture</span>
                    <strong>Read-only after preview binding</strong>
                  </div>
                  {historySourceMismatch ? (
                    <>
                      <div className="guard-item">
                        <span className="meta-label">Draft source</span>
                        <strong>{draftSource?.displayLabel ?? submittedSourceId}</strong>
                      </div>
                      <div className="state-callout state-callout-danger">
                        <p className="state-callout-title">Source mismatch blocked</p>
                        <p>
                          Selected draft source does not match the reopened candidate source, so
                          execution affordances stay unavailable.
                        </p>
                      </div>
                    </>
                  ) : null}
                </div>
              )}
              <label className="field-label" htmlFor="question">
                Natural-language question
              </label>
              <textarea
                defaultValue={submittedQuestion}
                disabled={queryLocked}
                id="question"
                name="question"
                placeholder="Ask a governed business question."
                rows={6}
              />
              {previewSubmission.status === "submitting" ? (
                <div className="state-callout state-callout-warning" role="status">
                  <p className="state-callout-title">Preview submission in progress</p>
                  <p>The draft is locked until the preview API returns an authoritative outcome.</p>
                </div>
              ) : null}
              {previewSubmission.status === "succeeded" ? (
                <div className="state-callout state-callout-success" role="status">
                  <p className="state-callout-title">Preview request accepted</p>
                  <p>
                    Request state {previewSubmission.requestState}; candidate state{" "}
                    {previewSubmission.candidateState}.
                  </p>
                </div>
              ) : null}
              {previewSubmission.status === "pending" ? (
                <div className="state-callout state-callout-warning" role="status">
                  <p className="state-callout-title">Preview generation pending</p>
                  <p>
                    Request state {previewSubmission.requestState}; candidate state{" "}
                    {previewSubmission.candidateState}. The shell stays in query review until SQL
                    preview is ready.
                  </p>
                </div>
              ) : null}
              {previewSubmission.status === "denied" ? (
                <div className="state-callout state-callout-danger" role="status">
                  <p className="state-callout-title">Preview denied</p>
                  <p>
                    Request state {previewSubmission.requestState}; candidate state{" "}
                    {previewSubmission.candidateState}. No successful SQL preview is displayed.
                  </p>
                </div>
              ) : null}
              {previewSubmission.status === "failed" ? (
                <div className="state-callout state-callout-danger" role="alert">
                  <p className="state-callout-title">{previewSubmission.code}</p>
                  <p>{previewSubmission.message}</p>
                </div>
              ) : null}
              {previewSubmission.status === "malformed" ? (
                <div className="state-callout state-callout-danger" role="alert">
                  <p className="state-callout-title">{previewSubmission.code}</p>
                  <p>{previewSubmission.message}</p>
                </div>
              ) : null}
              {previewSubmission.status === "unavailable" ? (
                <div className="state-callout state-callout-danger" role="alert">
                  <p className="state-callout-title">{previewSubmission.code}</p>
                  <p>{previewSubmission.message}</p>
                </div>
              ) : null}
              <div className="form-actions">
                <button disabled={queryLocked} type="submit">
                  {previewSubmission.status === "submitting"
                    ? "Submitting preview"
                    : "Submit for preview"}
                </button>
                {boundSourceId &&
                previewSubmission.status !== "submitting" &&
                !historySourceMismatch ? (
                  <a
                    className="ghost-link"
                    href={buildStateHref(
                      "completed",
                      submittedQuestion,
                      candidateSourceId,
                      historyHrefContext
                    )}
                  >
                    Open completed state
                  </a>
                ) : null}
              </div>
            </form>
          </section>
        </div>

        <aside className="support-column">
          <section className="surface surface-secondary">
            <div className="section-header">
              <div>
                <p className="eyebrow">Generated SQL</p>
                <h2 className="panel-title">Authoritative SQL preview</h2>
              </div>
              <span className="surface-badge surface-badge-code">Preview</span>
            </div>
            {renderCandidateSqlPreview(candidatePreview)}
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
              {workflowContext.guardStatus ? (
                <div className="guard-item">
                  <span className="meta-label">Guard status</span>
                  <strong>{workflowContext.guardStatus}</strong>
                </div>
              ) : null}
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
                <strong>Not connected</strong>
              </div>
              <div className="guard-item">
                <span className="meta-label">Candidate guard</span>
                <strong>{candidatePreview?.guardStatus ?? "No candidate record"}</strong>
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
            {renderResultContent(normalizedState, historyRunContext)}
          </section>
        </aside>
      </section>
    </main>
  );
}
