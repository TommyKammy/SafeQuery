"use client";

import { type FormEvent, useEffect, useState } from "react";
import { HealthStatusCard } from "./health-status-card";
import type { AnalystResponsePayload } from "../lib/analyst-response";
import type { HealthSnapshot } from "../lib/health";
import type {
  GovernanceBindingStatus,
  OperatorWorkflowAuditEvent,
  OperatorWorkflowCandidateAttempt,
  OperatorWorkflowExecutedEvidence,
  OperatorHistoryItem,
  OperatorWorkflowRevisionContext,
  OperatorWorkflowReviewEvidence,
  OperatorWorkflowRetrievedCitation,
  OperatorWorkflowSnapshot,
  SourceOption
} from "../lib/operator-workflow";

type WorkflowState =
  | "signin"
  | "query"
  | "preview"
  | "clarification_required"
  | "review_denied"
  | "completed"
  | "empty"
  | "insufficient_evidence"
  | "execution_denied"
  | "failed"
  | "canceled"
  | "results"
  | "error";

type CanonicalWorkflowState =
  | "signin"
  | "query"
  | "preview"
  | "clarification_required"
  | "review_denied"
  | "completed"
  | "empty"
  | "insufficient_evidence"
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
  state?: string;
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

type RevisionDraftContext = {
  candidateId?: string;
  itemType: "request" | "candidate" | "run";
  requestId?: string;
  runId?: string;
  sourceId: string;
};

type FirstRunGuidance = {
  body: string;
  title: string;
};

type OperatorRecoveryGuidance = {
  action: string;
  anchor: string;
  title: string;
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
      status: "clarification_required" | "denied" | "pending";
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

type ExecuteSubmissionStatus =
  | {
      status: "idle";
    }
  | {
      status: "executing";
    }
  | {
      code: string;
      message: string;
      status: "denied" | "failed";
    }
  | {
      candidateId: string;
      rowCount: number;
      status: "canceled" | "succeeded";
    };

type PreviewSubmissionResult = {
  auditEvents: OperatorWorkflowAuditEvent[];
  candidateId: string;
  candidateSql: string | null;
  candidateState: string;
  clarifyingQuestions: string[];
  datasetContractVersion: number | null;
  guardStatus: string;
  requestId: string;
  requestState: string;
  reviewEvidence: OperatorWorkflowReviewEvidence[];
  retrievedCitations: OperatorWorkflowRetrievedCitation[];
  revisionContext: RevisionDraftContext | null;
  schemaSnapshotVersion: number | null;
  semanticContractVersion: string | null;
  sourceId: string;
  sourceFamily: string | null;
  sourceFlavor: string | null;
};

type AuthoritativeCandidatePreview = {
  auditEvents: OperatorWorkflowAuditEvent[];
  candidateId: string;
  candidateSql: string | null;
  candidateState: string;
  clarifyingQuestions?: string[];
  datasetContractVersion?: number | null;
  executedEvidence: OperatorWorkflowExecutedEvidence[];
  guardStatus: string;
  requestId?: string;
  reviewEvidence: OperatorWorkflowReviewEvidence[];
  retrievedCitations: OperatorWorkflowRetrievedCitation[];
  schemaSnapshotVersion?: number | null;
  semanticContractVersion?: string | null;
  sourceId: string;
  sourceLabel?: string;
};

type AuthoritativeRunContext = {
  analystResponse: AnalystResponsePayload | null;
  auditEvents: OperatorWorkflowAuditEvent[];
  executedEvidence: OperatorWorkflowExecutedEvidence[];
  insufficientEvidence?: InsufficientEvidenceState | null;
  lifecycleState: string;
  lifecycleTimestamp: string;
  primaryDenyCode?: string | null;
  reviewEvidence: OperatorWorkflowReviewEvidence[];
  retrievedCitations: OperatorWorkflowRetrievedCitation[];
  resultTruncated?: boolean | null;
  resultRows?: ResultRow[];
  rowCount?: number | null;
  runIdentity: string;
  runState?: string | null;
  sourceLabel: string;
};

type ApiErrorEnvelope = {
  code: string;
  message: string;
};

type ExecuteSubmissionResult = {
  auditEvents: OperatorWorkflowAuditEvent[];
  candidateId: string;
  executedEvidence: OperatorWorkflowExecutedEvidence[];
  executionRunId?: string;
  insufficientEvidence?: InsufficientEvidenceState | null;
  resultTruncated: boolean;
  rows: ResultRow[];
  rowCount: number;
  sourceId: string;
};

type InsufficientEvidenceReason =
  | "no_rows"
  | "missing_columns"
  | "unsafe_truncation"
  | "blocking_validation_warnings";

type InsufficientEvidenceState = {
  answerText: string;
  nextAction: string;
  reason: InsufficientEvidenceReason;
};

type ResultCell = string | number | boolean | null;
type ResultRow = Record<string, ResultCell>;

const MAX_RENDERED_RESULT_ROWS = 10;
const MAX_RENDERED_RESULT_COLUMNS = 8;

const sensitiveResultFieldPattern =
  /(secret|token|password|credential|connection|string|session|local[_-]?path|filepath|file[_-]?path|private[_-]?key|api[_-]?key)/i;

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
  insufficient_evidence: {
    description: "Execution completed, but validation could not support an answer.",
    label: "Insufficient evidence"
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
    description: "The operator request has been staged as a business-readable answer plan.",
    label: "Answer plan"
  },
  clarification_required: {
    description:
      "SafeQuery needs the operator to clarify business intent before SQL generation or execution can continue.",
    label: "Clarification required"
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
  "clarification_required",
  "review_denied",
  "completed",
  "empty",
  "insufficient_evidence",
  "execution_denied",
  "failed",
  "canceled"
];

const FIRST_RUN_SETUP_GUIDE_HREF =
  "https://github.com/TommyKammy/SafeQuery/blob/main/docs/local-development.md#first-run-ui-empty-states";
const LOCAL_DEMO_SOURCE_ID = "demo-business-postgres";

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

function getFirstRunGuidance(snapshot: OperatorWorkflowSnapshot): FirstRunGuidance | null {
  if (snapshot.status === "unavailable" || snapshot.status === "malformed") {
    return {
      body:
        "Confirm backend health, migrations, demo source seed, and first-run doctor before using the product shell.",
      title: "Backend workflow unavailable"
    };
  }

  if (snapshot.status === "entitlement_denied") {
    return {
      body:
        "Confirm the signed-in operator has the dev/local entitlement binding for the selected source, then retry the workflow.",
      title: "Source entitlement not available"
    };
  }

  if (snapshot.status === "operator_read_forbidden") {
    return {
      body:
        "Confirm the signed-in operator has reviewer, support, or admin authority before reading the operator workflow.",
      title: "Operator workflow authority required"
    };
  }

  if (snapshot.status === "live" && snapshot.sources.length === 0) {
    return {
      body:
        "Run migrations, seed the demo source, then run the first-run doctor before submitting preview requests.",
      title: "Source registry not configured"
    };
  }

  return null;
}

function renderFirstRunGuidance(guidance: FirstRunGuidance) {
  return (
    <div className="first-run-panel">
      <h3>{guidance.title}</h3>
      <p>{guidance.body}</p>
      <a className="inline-link" href={FIRST_RUN_SETUP_GUIDE_HREF} rel="noreferrer" target="_blank">
        Open first-run setup guide
      </a>
    </div>
  );
}

function getOperatorRecoveryGuidance(
  state: CanonicalWorkflowState,
  snapshot: OperatorWorkflowSnapshot
): OperatorRecoveryGuidance | null {
  if (snapshot.status === "unavailable" || snapshot.status === "malformed") {
    return {
      action:
        "Retry after backend health, migrations, seed data, and first-run doctor pass.",
      anchor:
        "Use the authoritative SafeQuery workflow payload before trusting source, request, candidate, run, or audit context.",
      title:
        snapshot.status === "malformed" ? "Workflow data malformed" : "Workflow data unavailable"
    };
  }

  if (
    snapshot.status === "unauthenticated" ||
    snapshot.status === "session_invalid" ||
    snapshot.status === "csrf_failed" ||
    snapshot.status === "operator_read_forbidden" ||
    snapshot.status === "entitlement_denied"
  ) {
    return {
      action:
        snapshot.status === "operator_read_forbidden"
          ? "Use a signed-in operator with reviewer, support, or admin authority before retrying."
          : "Revise the session, request freshness, or entitlement binding before retrying.",
      anchor:
        snapshot.status === "operator_read_forbidden"
          ? "Use SafeQuery authority records as the prerequisite; do not infer reviewer or support authority from UI text or external evidence."
          : "Use SafeQuery auth and entitlement records as the prerequisite; do not infer access from UI text or external evidence.",
      title: "Workflow access blocked"
    };
  }

  if (state === "review_denied") {
    return {
      action: "Revise the request or source binding before retrying preview.",
      anchor:
        "Use the authoritative SafeQuery request and candidate record; do not treat advisory context as approval.",
      title: "Recovery: review denied"
    };
  }

  if (state === "clarification_required") {
    return {
      action: "Revise the request or choose one explicit business meaning before retrying preview.",
      anchor:
        "Use the clarifying questions attached to the SafeQuery review record; do not treat an ambiguous candidate as executable.",
      title: "Recovery: clarification required"
    };
  }

  if (state === "execution_denied") {
    return {
      action:
        "Inspect execute-time guard, approval freshness, and runbook state before retrying.",
      anchor:
        "Use the authoritative SafeQuery run and audit context; a prior preview does not authorize execution.",
      title: "Recovery: execution denied"
    };
  }

  if (state === "failed") {
    return {
      action: "Inspect the run record and audit trail before retrying execution.",
      anchor:
        "Use the authoritative SafeQuery run failure and audit events; do not infer success from partial rows or external logs.",
      title: "Recovery: failed run"
    };
  }

  if (state === "empty") {
    return {
      action: "Revise filters or business question before retrying.",
      anchor:
        "Use the authoritative SafeQuery completed run metadata; zero rows stay distinct from denial, failure, or cancellation.",
      title: "Recovery: empty result"
    };
  }

  if (state === "canceled") {
    return {
      action:
        "Retry only after confirming the cancellation reason and current runbook posture.",
      anchor:
        "Use the authoritative SafeQuery run lifecycle and audit context; do not reuse interrupted execution evidence as success.",
      title: "Recovery: canceled run"
    };
  }

  return null;
}

function renderOperatorRecoveryGuidance(guidance: OperatorRecoveryGuidance) {
  return (
    <section
      aria-label="Operator recovery guidance"
      className="surface surface-secondary"
    >
      <div className="section-header">
        <div>
          <p className="eyebrow">Recovery</p>
          <h2 className="panel-title">{guidance.title}</h2>
        </div>
        <span className="surface-badge surface-badge-code">Advisory</span>
      </div>
      <p className="section-copy">{guidance.action}</p>
      <p className="section-copy">
        {guidance.anchor} This guidance does not approve or execute the workflow.
      </p>
    </section>
  );
}

function findSourceOption(
  sourceOptions: SourceOption[],
  sourceId?: string
): SourceOption | undefined {
  return sourceOptions.find((source) => source.sourceId === sourceId);
}

function governanceBindingStateLabel(binding: GovernanceBindingStatus): string {
  return `${binding.role.replace("_", " ")}: ${binding.state}`;
}

function hasEntitlementAffectingGovernanceDrift(source?: SourceOption): boolean {
  return (
    source?.governanceBindings.some(
      (binding) => binding.affectsEntitlement && binding.state !== "valid"
    ) ?? false
  );
}

function renderGovernanceBindingStatuses(source?: SourceOption) {
  if (!source || source.governanceBindings.length === 0) {
    return null;
  }

  const hasDrift = hasEntitlementAffectingGovernanceDrift(source);
  return (
    <div
      aria-label="Governance binding status"
      className={`state-callout state-callout-${hasDrift ? "danger" : "empty"}`}
    >
      <p className="state-callout-title">
        {hasDrift ? "Governance binding review required" : "Governance bindings current"}
      </p>
      <div className="guard-list">
        {source.governanceBindings.map((binding) => (
          <div className="guard-item" key={`${source.sourceId}:${binding.role}`}>
            <span className="meta-label">{governanceBindingStateLabel(binding)}</span>
            <strong>{binding.summary}</strong>
            <span>{binding.recovery}</span>
          </div>
        ))}
      </div>
    </div>
  );
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

function parseDevSessionBootstrap(value: unknown): string | undefined {
  if (!isObject(value)) {
    return undefined;
  }

  return readRequiredString(value.csrf_token);
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

function parseAuditEvents(value: unknown): Record<string, unknown>[] {
  if (!isObject(value) || !isObject(value.audit) || !Array.isArray(value.audit.events)) {
    return [];
  }

  return value.audit.events.filter(isObject);
}

function readOptionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function readOptionalNonNegativeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

function readRequiredPositiveInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

function readStringArray(value: unknown): string[] | null {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value)) {
    return null;
  }

  const strings = value.filter((item): item is string => {
    return typeof item === "string" && item.trim().length > 0;
  });
  return strings.length === value.length ? strings : null;
}

function parsePreviewReviewEvidence(value: unknown): OperatorWorkflowReviewEvidence | null {
  if (!isObject(value)) {
    return null;
  }

  const auditEventId =
    readOptionalString(value.audit_event_id) ?? readOptionalString(value.auditEventId);
  const reviewContractVersion =
    readOptionalString(value.review_contract_version) ??
    readOptionalString(value.reviewContractVersion);
  const reviewDecisionId =
    readOptionalString(value.review_decision_id) ?? readOptionalString(value.reviewDecisionId);
  const reviewStatus =
    readOptionalString(value.review_status) ?? readOptionalString(value.reviewStatus);
  const assumptions = readStringArray(value.assumptions);
  const clarifyingQuestions =
    value.clarifying_questions === undefined
      ? readStringArray(value.clarifyingQuestions)
      : readStringArray(value.clarifying_questions);
  const riskFlags =
    value.risk_flags === undefined
      ? readStringArray(value.riskFlags)
      : readStringArray(value.risk_flags);

  if (
    !auditEventId ||
    !reviewContractVersion ||
    !reviewDecisionId ||
    !reviewStatus ||
    assumptions === null ||
    clarifyingQuestions === null ||
    riskFlags === null
  ) {
    return null;
  }

  return {
    auditEventId,
    assumptions,
    clarifyingQuestions,
    reviewContractVersion,
    reviewDecisionId,
    reviewStatus,
    riskFlags
  };
}

function parsePreviewAuditEvent(
  value: unknown,
  expectedSourceId: string
): OperatorWorkflowAuditEvent | null {
  if (!isObject(value)) {
    return null;
  }

  const eventId = readOptionalString(value.event_id) ?? readOptionalString(value.eventId);
  const eventType = readOptionalString(value.event_type) ?? readOptionalString(value.eventType);
  const occurredAt = readOptionalString(value.occurred_at) ?? readOptionalString(value.occurredAt);
  const requestId = readOptionalString(value.request_id) ?? readOptionalString(value.requestId);
  const sourceId = readOptionalString(value.source_id) ?? readOptionalString(value.sourceId);

  if (!eventId || !eventType || !occurredAt || !requestId || sourceId !== expectedSourceId) {
    return null;
  }

  return {
    candidateId:
      readOptionalString(value.query_candidate_id) ??
      readOptionalString(value.queryCandidateId) ??
      readOptionalString(value.candidate_id) ??
      readOptionalString(value.candidateId),
    candidateState:
      readOptionalString(value.candidate_state) ?? readOptionalString(value.candidateState),
    denialReason: readOptionalString(value.denial_reason) ?? readOptionalString(value.denialReason),
    eventId,
    eventType,
    executionRunId:
      readOptionalString(value.execution_run_id) ?? readOptionalString(value.executionRunId),
    guardDecision: readOptionalString(value.guard_decision) ?? readOptionalString(value.guardDecision),
    occurredAt,
    primaryDenyCode:
      readOptionalString(value.primary_deny_code) ?? readOptionalString(value.primaryDenyCode),
    requestId,
    resultTruncated:
      typeof value.result_truncated === "boolean"
        ? value.result_truncated
        : typeof value.resultTruncated === "boolean"
          ? value.resultTruncated
          : null,
    rowCount:
      readOptionalNonNegativeInteger(value.execution_row_count) ??
      readOptionalNonNegativeInteger(value.rowCount),
    semanticContractVersion:
      readOptionalString(value.semantic_contract_version) ??
      readOptionalString(value.semanticContractVersion),
    sourceId
  };
}

function parsePreviewRetrievedCitation(
  value: unknown,
  expectedSourceId: string
): OperatorWorkflowRetrievedCitation | null {
  if (!isObject(value)) {
    return null;
  }

  const assetId = readOptionalString(value.asset_id) ?? readOptionalString(value.assetId);
  const assetKind = readOptionalString(value.asset_kind) ?? readOptionalString(value.assetKind);
  const citationLabel =
    readOptionalString(value.citation_label) ?? readOptionalString(value.citationLabel);
  const sourceId = readOptionalString(value.source_id) ?? readOptionalString(value.sourceId);
  const sourceFamily =
    readOptionalString(value.source_family) ?? readOptionalString(value.sourceFamily);
  const sourceFlavor =
    readOptionalString(value.source_flavor) ?? readOptionalString(value.sourceFlavor);
  const canAuthorizeExecution =
    typeof value.can_authorize_execution === "boolean"
      ? value.can_authorize_execution
      : value.canAuthorizeExecution;

  if (
    value.authority !== "advisory_context" ||
    canAuthorizeExecution !== false ||
    !assetId ||
    !assetKind ||
    !citationLabel ||
    sourceId !== expectedSourceId ||
    !sourceFamily
  ) {
    return null;
  }

  return {
    assetId,
    assetKind,
    authority: "advisory_context",
    canAuthorizeExecution: false,
    citationLabel,
    datasetContractVersion:
      readRequiredPositiveInteger(value.dataset_contract_version) ??
      readRequiredPositiveInteger(value.datasetContractVersion),
    schemaSnapshotVersion:
      readRequiredPositiveInteger(value.schema_snapshot_version) ??
      readRequiredPositiveInteger(value.schemaSnapshotVersion),
    sourceId,
    sourceFamily,
    sourceFlavor: sourceFlavor ?? null
  };
}

function singleCitationContractVersion(
  citations: OperatorWorkflowRetrievedCitation[],
  key: "datasetContractVersion" | "schemaSnapshotVersion"
): number | null {
  const versions = new Set<number>();
  for (const citation of citations) {
    const version = citation[key];
    if (typeof version === "number" && Number.isInteger(version) && version > 0) {
      versions.add(version);
    }
  }

  return versions.size === 1 ? [...versions][0] : null;
}

function parsePreviewRetrievedCitationsFromValue(
  value: unknown,
  expectedSourceId: string
): OperatorWorkflowRetrievedCitation[] | null {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value)) {
    return null;
  }

  const citations: OperatorWorkflowRetrievedCitation[] = [];
  for (const item of value) {
    const citation = parsePreviewRetrievedCitation(item, expectedSourceId);
    if (citation === null) {
      return null;
    }
    citations.push(citation);
  }
  return citations;
}

function parsePreviewRetrievedCitationsFromEvents(
  events: unknown,
  expectedSourceId: string
): OperatorWorkflowRetrievedCitation[] | null {
  if (events === undefined) {
    return [];
  }
  if (!Array.isArray(events)) {
    return null;
  }

  const citations: OperatorWorkflowRetrievedCitation[] = [];
  for (const event of events) {
    if (!isObject(event)) {
      return null;
    }
    const eventCitations = parsePreviewRetrievedCitationsFromValue(
      event.retrieved_citations === undefined
        ? event.retrievedCitations
        : event.retrieved_citations,
      expectedSourceId
    );
    if (eventCitations === null) {
      return null;
    }
    citations.push(...eventCitations);
  }
  return citations;
}

function dedupeRetrievedCitations(
  citations: OperatorWorkflowRetrievedCitation[]
): OperatorWorkflowRetrievedCitation[] {
  const seen = new Set<string>();
  return citations.filter((citation) => {
    const key = `${citation.sourceId}:${citation.assetKind}:${citation.assetId}:${citation.citationLabel}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function dedupeStrings(values: string[]): string[] {
  return [...new Set(values)];
}

function parseBackendClarifyingQuestions(candidate: Record<string, unknown>): string[] {
  const intentMapping = isObject(candidate.intent_mapping)
    ? candidate.intent_mapping
    : isObject(candidate.intentMapping)
      ? candidate.intentMapping
      : null;

  return dedupeStrings(
    [
      readOptionalString(candidate.denial_reason) ?? readOptionalString(candidate.denialReason),
      intentMapping
        ? readOptionalString(intentMapping.clarification) ??
          readOptionalString(intentMapping.clarifying_question) ??
          readOptionalString(intentMapping.clarifyingQuestion)
        : null
    ].filter((item): item is string => item !== null)
  );
}

function parseExecuteAuditEvent(value: unknown): OperatorWorkflowAuditEvent | null {
  if (!isObject(value)) {
    return null;
  }

  const eventId = readOptionalString(value.event_id);
  const eventType = readOptionalString(value.event_type);
  const occurredAt = readOptionalString(value.occurred_at);
  const requestId = readOptionalString(value.request_id);
  const sourceId = readOptionalString(value.source_id);

  if (!eventId || !eventType || !occurredAt || !requestId || !sourceId) {
    return null;
  }

  return {
    candidateId: readOptionalString(value.query_candidate_id),
    candidateState: readOptionalString(value.candidate_state),
    denialReason: readOptionalString(value.denial_reason),
    eventId,
    eventType,
    executionRunId: null,
    guardDecision: readOptionalString(value.guard_decision),
    occurredAt,
    primaryDenyCode: readOptionalString(value.primary_deny_code),
    requestId,
    resultTruncated: typeof value.result_truncated === "boolean" ? value.result_truncated : null,
    rowCount: readOptionalNonNegativeInteger(value.execution_row_count),
    sourceId
  };
}

function parseExecuteAuditEvents(value: unknown): OperatorWorkflowAuditEvent[] {
  return parseAuditEvents(value)
    .map(parseExecuteAuditEvent)
    .filter((event): event is OperatorWorkflowAuditEvent => event !== null);
}

function isInsufficientEvidenceReason(value: unknown): value is InsufficientEvidenceReason {
  return (
    value === "no_rows" ||
    value === "missing_columns" ||
    value === "unsafe_truncation" ||
    value === "blocking_validation_warnings"
  );
}

function parseInsufficientEvidenceState(value: unknown): InsufficientEvidenceState | null {
  if (!isObject(value) || value.answer_state !== "insufficient_evidence") {
    return null;
  }

  const answerText = readRequiredString(value.answer_text);
  const nextAction = readRequiredString(value.next_action);
  const reason = value.insufficient_evidence_reason;
  if (!answerText || !nextAction || !isInsufficientEvidenceReason(reason)) {
    return null;
  }

  return {
    answerText,
    nextAction,
    reason
  };
}

function isResultCell(value: unknown): value is ResultCell {
  return (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  );
}

function parseExecuteRows(value: unknown): ResultRow[] | null {
  if (!Array.isArray(value)) {
    return null;
  }

  const rows: ResultRow[] = [];
  for (const item of value) {
    if (!isObject(item)) {
      return null;
    }

    const row: ResultRow = {};
    for (const [key, cell] of Object.entries(item)) {
      if (
        typeof key !== "string" ||
        key.trim().length === 0 ||
        sensitiveResultFieldPattern.test(key) ||
        !isResultCell(cell)
      ) {
        continue;
      }
      row[key] = cell;
    }
    rows.push(row);
  }

  return rows;
}

function buildExecutedEvidenceFromExecuteResponse(
  result: {
    auditEvents: OperatorWorkflowAuditEvent[];
    candidateId: string;
    resultTruncated: boolean;
    rowCount: number;
    sourceId: string;
  },
  metadata: Record<string, unknown>
): OperatorWorkflowExecutedEvidence[] {
  const completedEvent = result.auditEvents.find(
    (event) =>
      event.eventType === "execution_completed" &&
      event.candidateId === result.candidateId &&
      event.sourceId === result.sourceId
  );
  const sourceFamily = readOptionalString(metadata.source_family);
  const executionRunId = readOptionalString(metadata.execution_run_id);

  if (!completedEvent || !sourceFamily || !executionRunId) {
    return [];
  }

  return [
    {
      authority: "backend_execution_result",
      canAuthorizeExecution: false,
      candidateId: result.candidateId,
      executionRunId,
      executionAuditEventId: completedEvent.eventId,
      executionAuditEventType: "execution_completed",
      resultTruncated: result.resultTruncated,
      rowCount: result.rowCount,
      sourceFamily,
      sourceFlavor: readOptionalString(metadata.source_flavor),
      sourceId: result.sourceId
    }
  ];
}

function hasCanceledAuditEvent(value: unknown): boolean {
  return parseAuditEvents(value).some((event) => event.candidate_state === "canceled");
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
  const datasetContractVersion =
    readRequiredPositiveInteger(value.candidate.dataset_contract_version) ??
    readRequiredPositiveInteger(value.candidate.datasetContractVersion);
  const guardStatus = readRequiredString(value.candidate.guard_status);
  const requestState = readRequiredString(value.request.state);
  const schemaSnapshotVersion =
    readRequiredPositiveInteger(value.candidate.schema_snapshot_version) ??
    readRequiredPositiveInteger(value.candidate.schemaSnapshotVersion);
  const semanticContractVersion =
    readOptionalString(value.candidate.semantic_contract_version) ??
    readOptionalString(value.candidate.semanticContractVersion) ??
    readOptionalString(value.request.semantic_contract_version) ??
    readOptionalString(value.request.semanticContractVersion);
  const candidateState = readRequiredString(value.candidate.state);
  const sourceFamily =
    readOptionalString(value.candidate.source_family) ??
    readOptionalString(value.candidate.sourceFamily);
  const sourceFlavor =
    readOptionalString(value.candidate.source_flavor) ??
    readOptionalString(value.candidate.sourceFlavor);
  const hasSnakeReviewEvidence = Object.prototype.hasOwnProperty.call(
    value.candidate,
    "review_evidence"
  );
  const hasCamelReviewEvidence = Object.prototype.hasOwnProperty.call(
    value.candidate,
    "reviewEvidence"
  );
  const reviewEvidenceValue = hasSnakeReviewEvidence
    ? value.candidate.review_evidence
    : hasCamelReviewEvidence
      ? value.candidate.reviewEvidence
      : [];
  if (!Array.isArray(reviewEvidenceValue)) {
    return null;
  }
  const parsedReviewEvidence = reviewEvidenceValue.map(parsePreviewReviewEvidence);
  if (parsedReviewEvidence.some((item) => item === null)) {
    return null;
  }
  const reviewEvidence = parsedReviewEvidence as OperatorWorkflowReviewEvidence[];
  if (!isObject(value.audit) || !Array.isArray(value.audit.events)) {
    return null;
  }
  const auditEventsValue = value.audit.events;
  const parsedAuditEvents = auditEventsValue.map((event) =>
    parsePreviewAuditEvent(event, expectedSourceId)
  );
  if (parsedAuditEvents.some((item) => item === null)) {
    return null;
  }
  const auditEvents = parsedAuditEvents as OperatorWorkflowAuditEvent[];
  const directRetrievedCitations = parsePreviewRetrievedCitationsFromValue(
    value.candidate.retrieved_citations === undefined
      ? value.candidate.retrievedCitations
      : value.candidate.retrieved_citations,
    expectedSourceId
  );
  const auditRetrievedCitations = parsePreviewRetrievedCitationsFromEvents(
    auditEventsValue,
    expectedSourceId
  );
  if (directRetrievedCitations === null || auditRetrievedCitations === null) {
    return null;
  }
  const retrievedCitations = dedupeRetrievedCitations([
    ...directRetrievedCitations,
    ...auditRetrievedCitations
  ]);
  const clarifyingQuestions = parseBackendClarifyingQuestions(value.candidate);

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
    auditEvents,
    candidateId,
    candidateSql,
    candidateState,
    clarifyingQuestions,
    datasetContractVersion,
    guardStatus,
    requestId,
    requestState,
    reviewEvidence,
    retrievedCitations,
    revisionContext:
      parsePreviewRevisionContext(value.request.revision_context, expectedSourceId) ??
      parsePreviewRevisionContext(value.candidate.revision_context, expectedSourceId),
    schemaSnapshotVersion,
    semanticContractVersion,
    sourceId: expectedSourceId,
    sourceFamily,
    sourceFlavor: sourceFlavor ?? null
  };
}

function buildSubmittedCandidatePreview(
  result: PreviewSubmissionResult,
  sourceLabel: string
): AuthoritativeCandidatePreview {
  return {
    auditEvents: result.auditEvents,
    candidateId: result.candidateId,
    candidateSql: result.candidateSql,
    candidateState: result.candidateState,
    clarifyingQuestions: result.clarifyingQuestions,
    datasetContractVersion: result.datasetContractVersion,
    executedEvidence: [],
    guardStatus: result.guardStatus,
    requestId: result.requestId,
    reviewEvidence: result.reviewEvidence,
    retrievedCitations: result.retrievedCitations,
    schemaSnapshotVersion: result.schemaSnapshotVersion,
    semanticContractVersion: result.semanticContractVersion,
    sourceId: result.sourceId,
    sourceLabel
  };
}

function parsePreviewRevisionContext(
  value: unknown,
  expectedSourceId: string
): RevisionDraftContext | null {
  if (!isObject(value)) {
    return null;
  }

  const itemType = value.item_type;
  const sourceId = readOptionalString(value.source_id);
  if (
    (itemType !== "request" && itemType !== "candidate" && itemType !== "run") ||
    sourceId !== expectedSourceId
  ) {
    return null;
  }

  return {
    candidateId: readOptionalString(value.candidate_id) ?? undefined,
    itemType,
    requestId: readOptionalString(value.request_id) ?? undefined,
    runId: readOptionalString(value.run_id) ?? undefined,
    sourceId
  };
}

function parseExecuteSubmissionResult(
  value: unknown,
  expectedCandidateId: string,
  expectedSourceId: string
): ExecuteSubmissionResult | null {
  if (!isObject(value) || !isObject(value.metadata)) {
    return null;
  }

  const candidateId = readRequiredString(value.candidate_id);
  const sourceId = readRequiredString(value.source_id);
  const executionRunId = readRequiredString(value.metadata.execution_run_id);
  const rowCount = value.metadata.row_count;
  const resultTruncated = value.metadata.result_truncated;
  const rows = parseExecuteRows(value.rows);
  const insufficientEvidence = parseInsufficientEvidenceState(
    value.metadata.answer_summary
  );

  if (
    candidateId !== expectedCandidateId ||
    sourceId !== expectedSourceId ||
    typeof rowCount !== "number" ||
    !Number.isInteger(rowCount) ||
    rowCount < 0 ||
    typeof resultTruncated !== "boolean" ||
    rows === null ||
    rows.length > rowCount ||
    (!resultTruncated && rows.length !== rowCount)
  ) {
    return null;
  }

  const auditEvents = parseExecuteAuditEvents(value);
  const partialResult = {
    auditEvents,
    candidateId,
    resultTruncated,
    rowCount,
    sourceId
  };

  return {
    auditEvents,
    candidateId,
    executedEvidence: buildExecutedEvidenceFromExecuteResponse(partialResult, value.metadata),
    executionRunId,
    insufficientEvidence,
    resultTruncated,
    rows,
    rowCount,
    sourceId
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

function isClarificationRequiredPreviewState(result: PreviewSubmissionResult): boolean {
  const requestState = result.requestState.toLowerCase();
  const candidateState = result.candidateState.toLowerCase();

  return (
    requestState === "clarification_required" ||
    requestState === "needs_clarification" ||
    candidateState === "clarification_required" ||
    candidateState === "needs_clarification"
  );
}

function isReadyPreviewState(result: PreviewSubmissionResult): boolean {
  return result.candidateState.toLowerCase() === "preview_ready";
}

function canExecuteCandidate(
  state: CanonicalWorkflowState,
  candidatePreview: AuthoritativeCandidatePreview | null,
  hasSourceMismatch: boolean
): candidatePreview is AuthoritativeCandidatePreview {
  if (state !== "preview" || candidatePreview === null || hasSourceMismatch) {
    return false;
  }

  const candidateState = candidatePreview.candidateState.toLowerCase();
  const guardStatus = candidatePreview.guardStatus.toLowerCase();
  return (
    candidateState === "preview_ready" &&
    (guardStatus === "allow" || guardStatus === "passed")
  );
}

function candidateRequiresClarification(
  candidatePreview: AuthoritativeCandidatePreview | null
): boolean {
  const candidateState = candidatePreview?.candidateState.toLowerCase();
  return candidateState === "clarification_required" || candidateState === "needs_clarification";
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

    if (hasEntitlementAffectingGovernanceDrift(source)) {
      return {
        blockedReason:
          "Resolve entitlement-affecting governance binding status before preview can be requested.",
        source,
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

  if (hasEntitlementAffectingGovernanceDrift(source)) {
    return {
      blockedReason:
        "Resolve entitlement-affecting governance binding status before preview can be requested.",
      source,
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
      lifecycleState === "clarification_required" ||
      lifecycleState === "needs_clarification" ||
      guardStatus === "needs_clarification"
    ) {
      return "clarification_required";
    }

    if (
      lifecycleState === "review_denied" ||
      lifecycleState === "blocked" ||
      lifecycleState === "preview_denied" ||
      lifecycleState === "preview_generation_failed" ||
      lifecycleState === "preview_malformed" ||
      lifecycleState === "preview_unavailable" ||
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

  if (
    runState === "insufficient_evidence" ||
    lifecycleState === "insufficient_evidence"
  ) {
    return "insufficient_evidence";
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

  if (status === "operator_read_forbidden") {
    return "Reviewer or support authority is required before reading the operator workflow.";
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
  const candidate = findAuthoritativeCandidateHistoryItem(history, sourceId, historyRecordId);
  if (!candidate) {
    return null;
  }

  return {
    auditEvents: candidate.auditEvents,
    candidateId: candidate.recordId,
    candidateSql: candidate.candidateSql ?? null,
    candidateState: candidate.lifecycleState,
    executedEvidence: candidate.executedEvidence,
    guardStatus: candidate.guardStatus ?? "pending",
    requestId: candidate.requestId ?? undefined,
    reviewEvidence: candidate.reviewEvidence,
    retrievedCitations: candidate.retrievedCitations,
    semanticContractVersion: candidate.semanticContractVersion,
    sourceId: candidate.sourceId,
    sourceLabel: candidate.sourceLabel
  };
}

function findAuthoritativeCandidateHistoryItem(
  history: OperatorHistoryItem[],
  sourceId?: string,
  historyRecordId?: string
): OperatorHistoryItem | null {
  const candidates = history.filter((item) => item.itemType === "candidate");

  if (!historyRecordId) {
    return candidates.find((item) => !sourceId || item.sourceId === sourceId) ?? null;
  }

  const directCandidate = candidates.find((item) => item.recordId === historyRecordId);
  if (directCandidate) {
    return directCandidate;
  }

  if (!sourceId) {
    return null;
  }

  const requestCandidates = candidates.filter(
    (item) => item.sourceId === sourceId && item.requestId === historyRecordId
  );
  if (requestCandidates.length === 0) {
    return null;
  }

  return requestCandidates.sort(compareHistoryCandidateRecency)[0] ?? null;
}

function compareHistoryCandidateRecency(
  left: OperatorHistoryItem,
  right: OperatorHistoryItem
): number {
  const leftTime = Date.parse(left.occurredAt);
  const rightTime = Date.parse(right.occurredAt);
  if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
    return rightTime - leftTime;
  }

  return right.recordId.localeCompare(left.recordId);
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
    analystResponse: run.analystResponse,
    auditEvents: run.auditEvents,
    executedEvidence: run.executedEvidence,
    insufficientEvidence: run.insufficientEvidence ?? null,
    lifecycleState: run.lifecycleState,
    lifecycleTimestamp: run.occurredAt,
    primaryDenyCode: run.primaryDenyCode,
    reviewEvidence: run.reviewEvidence,
    retrievedCitations: run.retrievedCitations,
    resultTruncated: run.resultTruncated,
    rowCount: run.rowCount,
    runIdentity: run.recordId,
    runState: run.runState,
    sourceLabel: run.sourceLabel
  };
}

function renderSupplementalAnalystNarrative(analystResponse: AnalystResponsePayload | null) {
  if (!analystResponse) {
    return null;
  }

  return (
    <section className="surface surface-secondary" aria-label="supplemental analyst narrative">
      <div className="section-header">
        <div>
          <p className="eyebrow">Supplemental context</p>
          <h2 className="panel-title">Supplemental analyst narrative</h2>
        </div>
        <span className="surface-badge surface-badge-code">Non-authoritative</span>
      </div>
      <p className="section-copy">{analystResponse.narrative}</p>
      <div className="state-callout">
        <p className="state-callout-title">Workflow authority remains SafeQuery records</p>
        <p>
          This narrative cannot unlock execute, approval, export, audit, authorization, or
          governance decisions.
        </p>
      </div>
      <div className="evidence-list" aria-label="analyst run citations">
        {analystResponse.executedEvidence.map((evidence) => (
          <div className="evidence-item" key={evidence.executionAuditEventId}>
            <span className="meta-label">Executed evidence citation</span>
            <strong>{evidence.authority}</strong>
            <span>{evidence.sourceId}</span>
            <span>Candidate {evidence.candidateId}</span>
            <span>Run {evidence.executionRunId}</span>
            <span>Audit event {evidence.executionAuditEventId}</span>
            <span>{evidence.rowCount} rows</span>
            <span>Cannot authorize execution: {String(evidence.canAuthorizeExecution)}</span>
          </div>
        ))}
      </div>
      {analystResponse.retrievalCitations.length > 0 ? (
        <div className="evidence-list" aria-label="analyst retrieval citations">
          {analystResponse.retrievalCitations.map((citation) => (
            <div className="evidence-item" key={`${citation.assetKind}:${citation.assetId}`}>
              <span className="meta-label">Retrieval citation reference</span>
              <strong>{citation.citationLabel}</strong>
              <span>{citation.assetKind}</span>
              <span>{citation.assetId}</span>
              <span>{citation.authority}</span>
              <span>Cannot authorize execution: {String(citation.canAuthorizeExecution)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function revisionDraftFromSelectedContext(
  state: CanonicalWorkflowState,
  candidatePreview: AuthoritativeCandidatePreview | null,
  runContext: AuthoritativeRunContext | null,
  selectedHistoryItem?: OperatorHistoryItem,
  sourceId?: string
): RevisionDraftContext | null {
  if (
    (state === "review_denied" || state === "clarification_required") &&
    selectedHistoryItem?.itemType === "request" &&
    selectedHistoryItem.sourceId === sourceId &&
    isRevisableRequestLifecycleState(selectedHistoryItem.lifecycleState)
  ) {
    return {
      itemType: "request",
      requestId: selectedHistoryItem.recordId,
      sourceId: selectedHistoryItem.sourceId
    };
  }

  if ((state === "review_denied" || state === "clarification_required") && candidatePreview) {
    return {
      candidateId: candidatePreview.candidateId,
      itemType: "candidate",
      requestId: candidatePreview.requestId,
      sourceId: candidatePreview.sourceId
    };
  }

  if (
    runContext &&
    sourceId &&
    (state === "completed" ||
      state === "empty" ||
      state === "insufficient_evidence" ||
      state === "failed" ||
      state === "execution_denied")
  ) {
    const auditEvent = runContext.auditEvents.find(
      (event) => event.eventId === runContext.runIdentity
    );
    return {
      candidateId: auditEvent?.candidateId ?? undefined,
      itemType: "run",
      requestId: auditEvent?.requestId,
      runId: runContext.runIdentity,
      sourceId
    };
  }

  return null;
}

function isRevisableRequestLifecycleState(lifecycleState: string): boolean {
  const normalizedLifecycleState = lifecycleState.toLowerCase();
  return (
    normalizedLifecycleState === "blocked" ||
    normalizedLifecycleState === "clarification_required" ||
    normalizedLifecycleState === "needs_clarification" ||
    normalizedLifecycleState === "preview_denied" ||
    normalizedLifecycleState === "preview_generation_failed" ||
    normalizedLifecycleState === "preview_malformed" ||
    normalizedLifecycleState === "preview_unavailable"
  );
}

function revisionDraftFromHistoryContext(
  revisionContext?: OperatorWorkflowRevisionContext | null
): RevisionDraftContext | null {
  if (!revisionContext) {
    return null;
  }

  if (revisionContext.runId) {
    return {
      candidateId: revisionContext.candidateId ?? undefined,
      itemType: "run",
      requestId: revisionContext.requestId ?? undefined,
      runId: revisionContext.runId,
      sourceId: revisionContext.sourceId
    };
  }

  if (revisionContext.candidateId) {
    return {
      candidateId: revisionContext.candidateId,
      itemType: "candidate",
      requestId: revisionContext.requestId ?? undefined,
      sourceId: revisionContext.sourceId
    };
  }

  if (revisionContext.requestId) {
    return {
      itemType: "request",
      requestId: revisionContext.requestId,
      sourceId: revisionContext.sourceId
    };
  }

  return null;
}

function serializeRevisionDraft(revision: RevisionDraftContext | null) {
  if (!revision) {
    return undefined;
  }

  return {
    item_type: revision.itemType,
    request_id: revision.requestId,
    candidate_id: revision.candidateId,
    run_id: revision.runId
  };
}

function renderCandidateSqlPreview(preview: AuthoritativeCandidatePreview | null) {
  if (!preview) {
    return (
      <div className="placeholder-block">
        <p className="placeholder-title">No authoritative candidate selected</p>
        <p>
          SQL generation is disabled or still pending. Submit the question for preview or reopen a
          candidate history row before technical SQL details can be shown.
        </p>
      </div>
    );
  }

  if (!preview.candidateSql) {
    return (
      <div className="placeholder-block">
        <p className="placeholder-title">Canonical SQL pending</p>
        <p>
          Canonical SQL has not been generated for this candidate. SQL generation is disabled or
          still pending, so continue from the business-readable answer plan.
        </p>
      </div>
    );
  }

  return (
    <pre className="sql-preview">
      <code>{preview.candidateSql}</code>
    </pre>
  );
}

function formatStatusLabel(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderListOrPlaceholder(items: string[], placeholder: string) {
  if (items.length === 0) {
    return <p className="section-copy">{placeholder}</p>;
  }

  return (
    <ul className="answer-plan-list">
      {items.map((item, index) => (
        <li key={`${item}:${index}`}>{item}</li>
      ))}
    </ul>
  );
}

function renderBusinessAnswerPlan(
  preview: AuthoritativeCandidatePreview | null,
  question: string,
  sourceIdentity: string,
  retrievedCitations: OperatorWorkflowRetrievedCitation[],
  reviewEvidence: OperatorWorkflowReviewEvidence[],
  candidateAttempts: OperatorWorkflowCandidateAttempt[],
  executeEnabled: boolean
) {
  const latestReview = reviewEvidence[0];
  const latestAttempt =
    candidateAttempts.find((attempt) => attempt.candidateId === preview?.candidateId) ??
    candidateAttempts[0];
  const semanticContractVersion =
    preview?.semanticContractVersion ?? latestAttempt?.semanticContractVersion ?? null;
  const datasetContractVersion =
    preview?.datasetContractVersion ??
    latestAttempt?.datasetContractVersion ??
    singleCitationContractVersion(retrievedCitations, "datasetContractVersion");
  const schemaSnapshotVersion =
    preview?.schemaSnapshotVersion ??
    latestAttempt?.schemaSnapshotVersion ??
    singleCitationContractVersion(retrievedCitations, "schemaSnapshotVersion");
  const sourceEvidence = retrievedCitations.map((citation) => citation.citationLabel);
  const semanticEvidence = [
    semanticContractVersion ? `Semantic contract ${semanticContractVersion}` : null,
    datasetContractVersion !== null ? `Dataset contract v${datasetContractVersion}` : null,
    schemaSnapshotVersion !== null ? `Schema snapshot v${schemaSnapshotVersion}` : null,
    ...retrievedCitations.map(
      (citation) => `${formatStatusLabel(citation.assetKind)}: ${citation.citationLabel}`
    )
  ].filter((item): item is string => item !== null);
  const assumptions = latestReview?.assumptions ?? [];
  const reviewClarifyingQuestions = latestReview?.clarifyingQuestions ?? [];
  const clarifyingQuestions =
    reviewClarifyingQuestions.length > 0
      ? reviewClarifyingQuestions
      : (preview?.clarifyingQuestions ?? []);
  const clarificationRequired =
    clarifyingQuestions.length > 0 ||
    preview?.candidateState.toLowerCase() === "clarification_required" ||
    preview?.candidateState.toLowerCase() === "needs_clarification";
  const reviewStatus = latestReview
    ? `Review ${latestReview.reviewStatus.replace(/_/g, " ")}`
    : "Review evidence not provided";
  const safetyStatus = preview
    ? `Candidate ${preview.candidateState}; guard ${preview.guardStatus}`
    : "No candidate selected";
  const nextAction =
    preview === null
      ? "Submit the question for preview, then review the answer plan returned by SafeQuery."
      : clarificationRequired
        ? "Answer the clarifying questions, then submit a revised preview before execution."
      : executeEnabled
        ? "Review the answer plan, then execute the reviewed candidate when the business intent and safety status match the request."
        : "Review the answer plan and resolve the guard or candidate status before execution.";

  return (
    <section
      aria-label="Business-readable answer plan"
      className="surface surface-primary answer-plan-panel"
    >
      <div className="section-header">
        <div>
          <p className="eyebrow">Answer plan</p>
          <h2 className="panel-title">Business-readable answer plan</h2>
        </div>
        <span className={`surface-badge surface-badge-${executeEnabled ? "success" : "warning"}`}>
          {executeEnabled ? "Ready" : "Review"}
        </span>
      </div>
      <div className="answer-plan-grid">
        <div className="answer-plan-item answer-plan-item-wide">
          <span className="meta-label">What SafeQuery understood</span>
          <strong>{question}</strong>
          <p>
            SafeQuery will answer this as a governed business request, not as a raw SQL approval
            task.
          </p>
        </div>
        <div className="answer-plan-item">
          <span className="meta-label">Source and data used</span>
          <strong>{sourceIdentity}</strong>
          {renderListOrPlaceholder(
            sourceEvidence,
            "No retrieved source evidence was supplied with this candidate."
          )}
        </div>
        <div className="answer-plan-item">
          <span className="meta-label">Semantic mapping evidence</span>
          <strong>{semanticContractVersion ?? "No semantic contract version supplied"}</strong>
          {renderListOrPlaceholder(
            semanticEvidence,
            "Metric, dimension, and filter details were not supplied in the workflow payload."
          )}
        </div>
        <div className="answer-plan-item">
          <span className="meta-label">Assumptions</span>
          <strong>{assumptions.length > 0 ? "Review evidence supplied" : "No assumptions supplied"}</strong>
          {renderListOrPlaceholder(assumptions, "No review assumptions were supplied.")}
        </div>
        <div className="answer-plan-item">
          <span className="meta-label">Clarifying questions</span>
          <strong>
            {clarifyingQuestions.length > 0
              ? "Business clarification required"
              : "No clarification requested"}
          </strong>
          {renderListOrPlaceholder(
            clarifyingQuestions,
            "No clarifying questions were supplied."
          )}
        </div>
        <div className="answer-plan-item">
          <span className="meta-label">Safety and review status</span>
          <strong>{formatStatusLabel(reviewStatus)}</strong>
          <p>{safetyStatus}</p>
          {latestReview?.riskFlags.length
            ? renderListOrPlaceholder(latestReview.riskFlags, "")
            : null}
        </div>
        <div className="answer-plan-item answer-plan-item-wide">
          <span className="meta-label">Next action</span>
          <strong>{nextAction}</strong>
        </div>
      </div>
    </section>
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

  if (
    candidatePreview &&
    (state === "preview" ||
      state === "review_denied" ||
      state === "clarification_required")
  ) {
    return {
      candidateIdentity: candidatePreview.candidateId,
      candidateState: candidatePreview.candidateState,
      guardStatus: candidatePreview.guardStatus,
      requestIdentity: candidatePreview.requestId,
      sourceIdentity
    };
  }

  if (state === "preview" || state === "review_denied" || state === "clarification_required") {
    return {
      sourceIdentity
    };
  }

  if (
    runContext &&
    (state === "completed" ||
      state === "empty" ||
      state === "insufficient_evidence" ||
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
  if (
    state === "review_denied" ||
    state === "execution_denied" ||
    state === "failed"
  ) {
    return "danger";
  }

  if (state === "clarification_required") {
    return "warning";
  }

  if (state === "completed" || state === "empty") {
    return "success";
  }

  if (state === "insufficient_evidence") {
    return "warning";
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

  if (state === "clarification_required") {
    return "Clarification required before execution";
  }

  if (state === "completed") {
    return "Execution completed";
  }

  if (state === "empty") {
    return "Execution completed with no approved rows";
  }

  if (state === "insufficient_evidence") {
    return "Execution completed with insufficient evidence";
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

  if (state === "clarification_required") {
    return "SafeQuery cannot safely infer the business meaning yet. Execution stays unavailable until the operator revises the question or chooses one explicit meaning.";
  }

  if (state === "completed") {
    return "Result inspection stays tied to the reviewed candidate and run record so operators can distinguish executed evidence from nearby advisory context.";
  }

  if (state === "empty") {
    return "The result surface can represent a clean no-data outcome without restyling the rest of the page or hiding guard context.";
  }

  if (state === "insufficient_evidence") {
    return "Execution completed, but SafeQuery withheld the answer because validation could not support it. Follow the stated next action before trying again.";
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

  return "The shell stops at review boundaries unless an authoritative candidate record supplies guard posture and candidate context.";
}

function getResultTitle(state: CanonicalWorkflowState): string {
  if (state === "completed") {
    return "Completed result set";
  }

  if (state === "empty") {
    return "No rows returned";
  }

  if (state === "insufficient_evidence") {
    return "Insufficient evidence";
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

function resultColumns(rows: ResultRow[]): string[] {
  const columns: string[] = [];
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!columns.includes(key)) {
        columns.push(key);
      }
      if (columns.length >= MAX_RENDERED_RESULT_COLUMNS) {
        return columns;
      }
    }
  }
  return columns;
}

function renderResultRows(rows: ResultRow[], rowCount: number, resultTruncated: boolean) {
  if (rows.length === 0) {
    return null;
  }

  const displayedRows = rows.slice(0, MAX_RENDERED_RESULT_ROWS);
  const columns = resultColumns(displayedRows);
  const rowsTruncated = rows.length > displayedRows.length;

  if (columns.length === 0) {
    return (
      <div className="state-callout state-callout-empty">
        <p className="state-callout-title">Result rows contained no displayable fields</p>
        <p>All returned fields were outside the bounded display contract.</p>
      </div>
    );
  }

  return (
    <div className="result-table-wrap">
      <table aria-label="execute response result rows" className="result-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayedRows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{String(row[column] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rowsTruncated ? (
        <p className="section-copy">
          Showing {displayedRows.length} of {rows.length} rows attached to this bounded payload.
        </p>
      ) : null}
      {resultTruncated ? (
        <p className="section-copy">
          SafeQuery returned a bounded preview of {rows.length} displayed rows for {rowCount} rows
          reported by execution metadata; this is not complete dataset access.
        </p>
      ) : (
        <p className="section-copy">
          Showing bounded result rows attached to this selected run only.
        </p>
      )}
    </div>
  );
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
        <>
          <div className="state-callout state-callout-success">
            <p className="state-callout-title">
              {runContext.resultTruncated
                ? "Truncated bounded result metadata"
                : "Bounded result metadata"}
            </p>
            <p>
              {runContext.rowCount} rows reported for this selected run; result payload{" "}
              {runContext.resultTruncated
                ? "was truncated by SafeQuery display limits."
                : "was not truncated."}
            </p>
          </div>
          {renderResultRows(
            runContext.resultRows ?? [],
            runContext.rowCount,
            runContext.resultTruncated
          )}
        </>
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
      <>
        <div className="state-callout state-callout-empty">
          <p className="state-callout-title">Empty result state reached</p>
          <p>
            The approved workflow executed successfully and returned zero rows. This is distinct
            from denied or failed execution, and the candidate and run context remain attached for
            revision.
          </p>
        </div>
        {runContext?.rowCount === 0 && runContext.resultTruncated === false ? (
          <div className="state-callout state-callout-success">
            <p className="state-callout-title">Bounded result metadata</p>
            <p>0 rows reported for this selected run; result payload was not truncated.</p>
          </div>
        ) : null}
      </>
    );
  }

  if (state === "insufficient_evidence") {
    const reasonLabel = runContext?.insufficientEvidence?.reason.replaceAll("_", " ");
    return (
      <div className="state-callout state-callout-warning">
        <p className="state-callout-title">Insufficient evidence state reached</p>
        <p>
          {runContext?.insufficientEvidence?.answerText ??
            "SafeQuery completed execution, but validation could not support an answer."}
        </p>
        {reasonLabel ? <p>Reason: {reasonLabel}.</p> : null}
        {runContext?.insufficientEvidence?.nextAction ? (
          <p>Next action: {runContext.insufficientEvidence.nextAction.replaceAll("_", " ")}.</p>
        ) : null}
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
        Submit the question to move into answer plan review. Results remain unavailable until
        execution returns authoritative rows.
      </p>
    </div>
  );
}

function renderAuditEvidencePanel(
  auditEvents: OperatorWorkflowAuditEvent[],
  executedEvidence: OperatorWorkflowExecutedEvidence[],
  retrievedCitations: OperatorWorkflowRetrievedCitation[],
  reviewEvidence: OperatorWorkflowReviewEvidence[],
  history: OperatorHistoryItem[],
  question: string
) {
  function findNavigationTarget(
    itemType: OperatorHistoryItem["itemType"],
    recordId: string,
    sourceId: string
  ): OperatorHistoryItem | undefined {
    return history.find(
      (item) =>
        item.itemType === itemType &&
        item.recordId === recordId &&
        item.sourceId === sourceId
    );
  }

  function renderHistoryNavigation(
    itemType: OperatorHistoryItem["itemType"],
    recordId: string,
    sourceId: string
  ) {
    const target = findNavigationTarget(itemType, recordId, sourceId);
    if (!target) {
      return <span>{`${itemType[0].toUpperCase()}${itemType.slice(1)} ${recordId}`}</span>;
    }

    return (
      <a
        className="inline-link"
        href={buildStateHref(historyItemToState(target), target.label || question, target.sourceId, {
          historyItemType: target.itemType,
          historyRecordId: target.recordId
        })}
      >
        Open {itemType} {recordId}
      </a>
    );
  }

  return (
    <section className="surface surface-secondary">
      <div className="section-header">
        <div>
          <p className="eyebrow">Audit and evidence</p>
          <h2 className="panel-title">Operator evidence context</h2>
        </div>
        <span className="surface-badge surface-badge-code">Read only</span>
      </div>

      {auditEvents.length === 0 &&
      executedEvidence.length === 0 &&
      retrievedCitations.length === 0 &&
      reviewEvidence.length === 0 ? (
        <div className="placeholder-block">
          <p className="placeholder-title">No audit evidence selected</p>
          <p>Open a history row with persisted audit context to inspect lifecycle evidence.</p>
        </div>
      ) : null}

      {auditEvents.length > 0 ? (
        <div className="evidence-list" aria-label="audit lifecycle events">
          {auditEvents.map((event) => (
            <div className="evidence-item" key={event.eventId}>
              <span className="meta-label">Audit event</span>
              <strong>{event.eventType}</strong>
              <span>{event.eventId}</span>
              <span>{event.occurredAt}</span>
              {renderHistoryNavigation("request", event.requestId, event.sourceId)}
              {event.candidateId
                ? renderHistoryNavigation("candidate", event.candidateId, event.sourceId)
                : null}
              {renderHistoryNavigation(
                "run",
                event.executionRunId ?? event.eventId,
                event.sourceId
              )}
              {event.rowCount !== null ? <span>{event.rowCount} rows</span> : null}
              {event.resultTruncated !== null ? (
                <span>{event.resultTruncated ? "Result truncated" : "Result not truncated"}</span>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {executedEvidence.length > 0 ? (
        <div className="evidence-list" aria-label="executed evidence">
          {executedEvidence.map((evidence) => (
            <div className="evidence-item" key={evidence.executionAuditEventId}>
              <span className="meta-label">Executed evidence</span>
              <strong>{evidence.authority}</strong>
              <span>{evidence.sourceId}</span>
              {renderHistoryNavigation("candidate", evidence.candidateId, evidence.sourceId)}
              {renderHistoryNavigation("run", evidence.executionRunId, evidence.sourceId)}
              <span>{evidence.rowCount} rows</span>
              <span>{evidence.resultTruncated ? "Result truncated" : "Result not truncated"}</span>
              <span>Cannot authorize execution: {String(evidence.canAuthorizeExecution)}</span>
            </div>
          ))}
        </div>
      ) : null}

      {retrievedCitations.length > 0 ? (
        <div className="evidence-list" aria-label="retrieved citation context">
          {retrievedCitations.map((citation) => (
            <div className="evidence-item" key={`${citation.assetKind}:${citation.assetId}`}>
              <span className="meta-label">Retrieved citation context</span>
              <strong>{citation.citationLabel}</strong>
              <span>{citation.assetKind}</span>
              <span>{citation.assetId}</span>
              <span>{citation.authority}</span>
              <span>Cannot authorize execution: {String(citation.canAuthorizeExecution)}</span>
            </div>
          ))}
        </div>
      ) : null}

      {reviewEvidence.length > 0 ? (
        <div className="evidence-list" aria-label="review evidence">
          {reviewEvidence.map((review) => (
            <div className="evidence-item" key={review.reviewDecisionId}>
              <span className="meta-label">Review evidence</span>
              <strong>{review.reviewStatus}</strong>
              <span>{review.reviewDecisionId}</span>
              <span>{review.reviewContractVersion}</span>
              <span>Audit event {review.auditEventId}</span>
              {review.assumptions.map((assumption, index) => (
                <span key={`${review.reviewDecisionId}:assumption:${index}`}>{assumption}</span>
              ))}
              {review.riskFlags.map((risk, index) => (
                <span key={`${review.reviewDecisionId}:risk:${index}`}>{risk}</span>
              ))}
              {review.clarifyingQuestions.map((question, index) => (
                <span key={`${review.reviewDecisionId}:clarifying:${index}`}>{question}</span>
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function attemptTone(attempt: OperatorWorkflowCandidateAttempt): "success" | "danger" | "warning" {
  const candidateState = attempt.candidateState.toLowerCase();
  const guardStatus = attempt.guardStatus.toLowerCase();

  if (attempt.executed || attempt.approved) {
    return "success";
  }

  if (
    candidateState === "blocked" ||
    candidateState === "invalidated" ||
    candidateState === "stale" ||
    guardStatus === "blocked" ||
    guardStatus === "invalidated" ||
    guardStatus === "requires_revalidation"
  ) {
    return "danger";
  }

  return "warning";
}

function renderCandidateAttemptComparison(attempts: OperatorWorkflowCandidateAttempt[]) {
  if (attempts.length < 2) {
    return null;
  }

  return (
    <section className="surface surface-secondary">
      <div className="section-header">
        <div>
          <p className="eyebrow">Candidate attempts</p>
          <h2 className="panel-title">Guard outcome comparison</h2>
        </div>
        <span className="surface-badge surface-badge-code">Read only</span>
      </div>
      <div className="attempt-list" aria-label="candidate attempt guard comparison">
        {attempts.map((attempt) => (
          <div
            className={`attempt-item attempt-item-${attemptTone(attempt)}`}
            key={attempt.candidateId}
          >
            <div className="attempt-heading">
              <strong>{attempt.candidateId}</strong>
              <span className={`surface-badge surface-badge-${attemptTone(attempt)}`}>
                {attempt.executed
                  ? "Executed"
                  : attempt.approved
                    ? "Approved"
                    : attempt.candidateState}
              </span>
            </div>
            <span>Request {attempt.requestId}</span>
            <span>
              Guard {attempt.guardStatus}
              {attempt.guardDecision ? ` / ${attempt.guardDecision}` : ""}
            </span>
            {attempt.primaryDenyCode ? <span>Deny code: {attempt.primaryDenyCode}</span> : null}
            {attempt.denialReason ? <span>Reason: {attempt.denialReason}</span> : null}
            <span>
              {attempt.sourceId} / {attempt.sourceFamily}
              {attempt.sourceFlavor ? ` / ${attempt.sourceFlavor}` : ""}
            </span>
            <span>
              Contract v{attempt.datasetContractVersion}; schema v{attempt.schemaSnapshotVersion}
            </span>
            {attempt.semanticContractVersion ? (
              <span>Semantic contract {attempt.semanticContractVersion}</span>
            ) : null}
            <span>{attempt.occurredAt}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function renderStatePanel(
  state: CanonicalWorkflowState,
  question: string,
  sourceId?: string,
  canOpenCompleted = false,
  context?: WorkflowHrefContext,
  onStartRevision?: () => void
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
        <h2>Answer plan preview</h2>
        <p className="section-copy">
          Query submission lands here first so business intent, source evidence, assumptions,
          review status, and next action can be reviewed before execution.
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
          {onStartRevision ? (
            <button className="ghost-button" onClick={onStartRevision} type="button">
              Revise attempt
            </button>
          ) : null}
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
          {onStartRevision ? (
            <button className="action-button" onClick={onStartRevision} type="button">
              Revise attempt
            </button>
          ) : null}
          <a className="ghost-link" href={buildStateHref("preview", question, sourceId)}>
            Back to answer plan
          </a>
        </div>
      </div>
    );
  }

  if (state === "insufficient_evidence") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Validation held</p>
        <h2>Insufficient evidence state</h2>
        <p className="section-copy">
          Execution completed, but validation could not support an answer. The operator must
          revise the query, source, or validation inputs before treating rows as evidence.
        </p>
        <div className="action-row">
          {onStartRevision ? (
            <button className="action-button" onClick={onStartRevision} type="button">
              Revise attempt
            </button>
          ) : null}
          <a className="ghost-link" href={buildStateHref("preview", question, sourceId)}>
            Back to answer plan
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
          {onStartRevision ? (
            <button className="action-button" onClick={onStartRevision} type="button">
              Revise attempt
            </button>
          ) : null}
          <a className="ghost-link" href={buildStateHref("preview", question, sourceId)}>
            Back to answer plan
          </a>
        </div>
      </div>
    );
  }

  if (state === "clarification_required") {
    return (
      <div className="state-hero">
        <p className="eyebrow">Intent clarification</p>
        <h2>Clarification required state</h2>
        <p className="section-copy">
          SafeQuery found business intent it cannot safely resolve. Answer the clarifying
          questions or choose one explicit meaning before requesting a new preview.
        </p>
        <div className="action-row">
          {onStartRevision ? (
            <button className="action-button" onClick={onStartRevision} type="button">
              Revise attempt
            </button>
          ) : null}
          {onStartRevision ? (
            <button className="ghost-button" onClick={onStartRevision} type="button">
              Choose meaning
            </button>
          ) : (
            <a className="ghost-link" href={buildStateHref("query", question, sourceId)}>
              Choose meaning
            </a>
          )}
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
          {onStartRevision ? (
            <button className="ghost-button" onClick={onStartRevision} type="button">
              Revise attempt
            </button>
          ) : null}
          <a className="action-link" href={buildStateHref("preview", question, sourceId)}>
            Back to answer plan
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
          {onStartRevision ? (
            <button className="ghost-button" onClick={onStartRevision} type="button">
              Revise attempt
            </button>
          ) : null}
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
          <a className="ghost-link" href={buildStateHref("preview", question, sourceId)}>
            Back to answer plan
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
        The custom shell is now SafeQuery-owned. Question input, answer planning, guard status,
        technical review, and results are separated into stable surfaces before real execution
        wiring is added.
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
  const [executeSubmission, setExecuteSubmission] = useState<ExecuteSubmissionStatus>({
    status: "idle"
  });
  const [submittedCandidatePreview, setSubmittedCandidatePreview] =
    useState<AuthoritativeCandidatePreview | null>(null);
  const [submittedRunContext, setSubmittedRunContext] = useState<AuthoritativeRunContext | null>(
    null
  );
  const [submittedQuestion, setSubmittedQuestion] = useState(question);
  const [submittedSourceId, setSubmittedSourceId] = useState(sourceId);
  const [submittedState, setSubmittedState] = useState(requestedState);
  const [revisionDraft, setRevisionDraft] = useState<RevisionDraftContext | null>(null);
  const [applicationCsrfToken, setApplicationCsrfToken] = useState<string | undefined>();

  useEffect(() => {
    setSubmittedQuestion(question);
    setSubmittedSourceId(sourceId);
    setSubmittedState(requestedState);
    setPreviewSubmission({ status: "idle" });
    setExecuteSubmission({ status: "idle" });
    setSubmittedCandidatePreview(null);
    setSubmittedRunContext(null);
    setRevisionDraft(null);
  }, [question, requestedState, sourceId]);

  const sourceBinding = resolveSourceBinding(
    operatorWorkflow.sources,
    submittedState,
    submittedSourceId
  );
  const normalizedState = sourceBinding.state;
  const activeState = workflowStates[normalizedState];
  const queryLocked =
    normalizedState === "signin" ||
    previewSubmission.status === "submitting" ||
    executeSubmission.status === "executing";
  const guardTone = getGuardTone(normalizedState);
  const historyCandidatePreview = findAuthoritativeCandidatePreview(
    operatorWorkflow.history,
    submittedSourceId,
    historyRecordId
  );
  const selectedHistoryRunContext = findAuthoritativeRunContext(
    operatorWorkflow.history,
    submittedSourceId,
    historyRecordId
  );
  const historyRunContext = submittedRunContext ?? selectedHistoryRunContext;
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
  const executeEnabled = canExecuteCandidate(
    normalizedState,
    candidatePreview,
    historySourceMismatch
  );
  const executeControlVisible =
    candidatePreview !== null &&
    normalizedState !== "clarification_required" &&
    !candidateRequiresClarification(candidatePreview);
  const historyHrefContext =
    (normalizedState === "preview" ||
      normalizedState === "clarification_required") &&
    historyRecordId &&
    historyCandidatePreview
      ? {
          historyItemType: "candidate" as const,
          historyRecordId: historyCandidatePreview.candidateId
        }
      : undefined;
  const selectedEvidenceContext =
    normalizedState === "preview" ||
    normalizedState === "review_denied" ||
    normalizedState === "clarification_required"
      ? candidatePreview
      : submittedRunContext ?? selectedHistoryRunContext ?? candidatePreview;
  const selectedAuditEvents = selectedEvidenceContext?.auditEvents ?? [];
  const selectedExecutedEvidence = selectedEvidenceContext?.executedEvidence ?? [];
  const selectedRetrievedCitations = selectedEvidenceContext?.retrievedCitations ?? [];
  const selectedReviewEvidence = selectedEvidenceContext?.reviewEvidence ?? [];
  const firstRunGuidance = getFirstRunGuidance(operatorWorkflow);
  const operatorRecoveryGuidance = getOperatorRecoveryGuidance(
    normalizedState,
    operatorWorkflow
  );
  const selectedHistoryItem = historyRecordId
    ? operatorWorkflow.history.find((item) => item.recordId === historyRecordId)
    : undefined;
  const selectedCandidateAttemptHistory =
    selectedHistoryItem ??
    (candidatePreview
      ? operatorWorkflow.history.find((item) => item.recordId === candidatePreview.candidateId)
      : undefined);
  const selectedCandidateAttempts = selectedCandidateAttemptHistory?.candidateAttempts ?? [];
  const selectedAnswerPlanCandidateAttempts = submittedCandidatePreview
    ? []
    : selectedCandidateAttempts;
  const selectedRevisionDraft = revisionDraftFromSelectedContext(
    normalizedState,
    candidatePreview,
    historyRunContext,
    selectedHistoryItem,
    submittedSourceId
  );
  const selectedRevisionContext =
    revisionDraftFromHistoryContext(selectedHistoryItem?.revisionContext) ?? revisionDraft;

  function startRevision() {
    const nextRevisionDraft = selectedRevisionDraft;
    if (!nextRevisionDraft) {
      return;
    }
    setRevisionDraft(nextRevisionDraft);
    setSubmittedQuestion(submittedQuestion);
    setSubmittedSourceId(submittedSourceId ?? nextRevisionDraft.sourceId);
    setSubmittedState("query");
    setPreviewSubmission({ status: "idle" });
    setExecuteSubmission({ status: "idle" });
  }

  async function resolveApplicationCsrfToken(): Promise<string | undefined> {
    const existingToken = readCsrfToken() ?? applicationCsrfToken;
    if (existingToken) {
      return existingToken;
    }

    try {
      const response = await fetch(`${apiUrl}/auth/dev/session`, {
        credentials: "include",
        method: "POST"
      });
      if (!response.ok) {
        return undefined;
      }

      const token = parseDevSessionBootstrap(await response.json());
      if (token) {
        setApplicationCsrfToken(token);
      }
      return token;
    } catch {
      return undefined;
    }
  }

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

    if (hasEntitlementAffectingGovernanceDrift(selectedSource)) {
      setPreviewSubmission({
        code: "preview_governance_binding_review_required",
        message:
          "Resolve entitlement-affecting governance binding status before preview can be requested.",
        status: "failed"
      });
      return;
    }

    setPreviewSubmission({ status: "submitting" });

    const headers: Record<string, string> = {
      "content-type": "application/json"
    };
    const csrfToken = await resolveApplicationCsrfToken();
    if (csrfToken) {
      headers["x-safequery-csrf"] = csrfToken;
    }

    try {
      const response = await fetch(`${apiUrl}/requests/preview`, {
        body: JSON.stringify({
          question: submittedQuestionText,
          source_id: selectedSourceId,
          revise_from: serializeRevisionDraft(revisionDraft)
        }),
        credentials: "include",
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
      setSubmittedRunContext(null);

      if (isClarificationRequiredPreviewState(result)) {
        setSubmittedQuestion(submittedQuestionText);
        setSubmittedSourceId(result.sourceId);
        setSubmittedState("clarification_required");
        setRevisionDraft(result.revisionContext ?? revisionDraft);
        setSubmittedCandidatePreview(
          buildSubmittedCandidatePreview(result, selectedSource.displayLabel)
        );
        setPreviewSubmission({
          candidateState: result.candidateState,
          requestState: result.requestState,
          sourceId: result.sourceId,
          status: "clarification_required"
        });
        return;
      }

      if (isDeniedPreviewState(result)) {
        setSubmittedQuestion(submittedQuestionText);
        setSubmittedSourceId(result.sourceId);
        setSubmittedState("review_denied");
        setRevisionDraft(result.revisionContext ?? revisionDraft);
        setSubmittedCandidatePreview(
          buildSubmittedCandidatePreview(result, selectedSource.displayLabel)
        );
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
        setRevisionDraft(result.revisionContext ?? revisionDraft);
        setSubmittedCandidatePreview(
          buildSubmittedCandidatePreview(result, selectedSource.displayLabel)
        );
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
      setRevisionDraft(result.revisionContext ?? revisionDraft);
      setSubmittedCandidatePreview(
        buildSubmittedCandidatePreview(result, selectedSource.displayLabel)
      );
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

  async function executeCandidate() {
    if (!executeEnabled || !submittedSourceId) {
      return;
    }

    setExecuteSubmission({ status: "executing" });

    const headers: Record<string, string> = {
      "content-type": "application/json"
    };
    const csrfToken = await resolveApplicationCsrfToken();
    if (csrfToken) {
      headers["x-safequery-csrf"] = csrfToken;
    }

    try {
      const response = await fetch(`${apiUrl}/candidates/${candidatePreview.candidateId}/execute`, {
        body: JSON.stringify({
          selected_source_id: candidatePreview.sourceId
        }),
        credentials: "include",
        headers,
        method: "POST"
      });
      let payload: unknown;
      try {
        payload = (await response.json()) as unknown;
      } catch {
        setSubmittedState("failed");
        setExecuteSubmission({
          code: "execution_unavailable",
          message: "Candidate execution did not return an authoritative payload.",
          status: "failed"
        });
        return;
      }

      if (!response.ok) {
        const error = parseApiErrorEnvelope(payload);
        if (hasCanceledAuditEvent(payload)) {
          setSubmittedState("canceled");
          setSubmittedRunContext({
            analystResponse: null,
            auditEvents: [],
            executedEvidence: [],
            lifecycleState: "canceled",
            lifecycleTimestamp: new Date().toISOString(),
            reviewEvidence: candidatePreview.reviewEvidence,
            retrievedCitations: [],
            runIdentity: candidatePreview.candidateId,
            runState: "canceled",
            sourceLabel:
              candidatePreview.sourceLabel ??
              sourceBinding.source?.displayLabel ??
              candidatePreview.sourceId
          });
          setExecuteSubmission({
            candidateId: candidatePreview.candidateId,
            rowCount: 0,
            status: "canceled"
          });
          return;
        }

        if (error?.code === "execution_denied") {
          setSubmittedState("execution_denied");
          setExecuteSubmission({
            code: error.code,
            message: error.message,
            status: "denied"
          });
          return;
        }

        setSubmittedState("failed");
        setExecuteSubmission({
          code: error?.code ?? "execution_unavailable",
          message: error?.message ?? "Candidate execution is unavailable.",
          status: "failed"
        });
        return;
      }

      const result = parseExecuteSubmissionResult(
        payload,
        candidatePreview.candidateId,
        candidatePreview.sourceId
      );
      if (!result) {
        setSubmittedState("failed");
        setExecuteSubmission({
          code: "malformed_execute_response",
          message: "Execute response did not match the selected candidate and source binding.",
          status: "failed"
        });
        return;
      }

      const nextState = result.insufficientEvidence
        ? "insufficient_evidence"
        : result.rowCount === 0
          ? "empty"
          : "completed";
      setSubmittedState(nextState);
      setSubmittedRunContext({
        analystResponse: null,
        auditEvents: result.auditEvents,
        executedEvidence: result.executedEvidence,
        insufficientEvidence: result.insufficientEvidence ?? null,
        lifecycleState: nextState,
        lifecycleTimestamp: new Date().toISOString(),
        reviewEvidence: candidatePreview.reviewEvidence,
        retrievedCitations: [],
        resultTruncated: result.resultTruncated,
        resultRows: result.rows,
        rowCount: result.rowCount,
        runIdentity: result.executionRunId ?? result.candidateId,
        runState: nextState,
        sourceLabel:
          candidatePreview.sourceLabel ?? sourceBinding.source?.displayLabel ?? result.sourceId
      });
      setExecuteSubmission({
        candidateId: result.candidateId,
        rowCount: result.rowCount,
        status: "succeeded"
      });
    } catch {
      setSubmittedState("failed");
      setExecuteSubmission({
        code: "execution_unavailable",
        message: "Candidate execution transport is unavailable.",
        status: "failed"
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
            Operator shell for governed question review, answer planning, and execution posture.
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
            {firstRunGuidance ? renderFirstRunGuidance(firstRunGuidance) : null}
            <div className="history-list">
              {operatorWorkflow.history.length > 0 ? (
                operatorWorkflow.history.map(renderHistoryItem)
              ) : operatorWorkflow.status === "live" && operatorWorkflow.sources.length > 0 ? (
                <div className="placeholder-block">
                  <h3 className="placeholder-title">No workflow history yet</h3>
                  <p>
                    Recent previews will appear here. Submit a preview request against an active
                    source. SafeQuery will show request, candidate, and run summaries here only
                    after the backend returns them.
                  </p>
                </div>
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
              historyHrefContext,
              selectedRevisionDraft ? startRevision : undefined
            )}
          </section>

          {normalizedState === "preview" ||
          normalizedState === "review_denied" ||
          normalizedState === "clarification_required"
            ? renderBusinessAnswerPlan(
                candidatePreview,
                submittedQuestion,
                workflowContext.sourceIdentity,
                selectedRetrievedCitations,
                selectedReviewEvidence,
                selectedAnswerPlanCandidateAttempts,
                executeEnabled
              )
            : null}

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
                  {revisionDraft ? (
                    <div className="state-callout state-callout-warning">
                      <p className="state-callout-title">Revised attempt draft</p>
                      <p>
                        New preview will keep prior context from {revisionDraft.itemType}{" "}
                        {revisionDraft.runId ?? revisionDraft.candidateId ?? revisionDraft.requestId}.
                      </p>
                    </div>
                  ) : null}
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
                    {boundSourceId === LOCAL_DEMO_SOURCE_ID
                      ? "The local demo source is selected for this development run. Preview does not execute a query; it stages a business-readable answer plan for review."
                      : "Choose one explicit source before preview submission. Preview does not execute a query, and SafeQuery does not infer or auto-route the initial source binding."}
                  </p>
                  {renderGovernanceBindingStatuses(sourceBinding.source)}
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
              {previewSubmission.status === "clarification_required" ? (
                <div className="state-callout state-callout-warning" role="status">
                  <p className="state-callout-title">Clarification required</p>
                  <p>
                    Request state {previewSubmission.requestState}; candidate state{" "}
                    {previewSubmission.candidateState}. Answer the clarifying question before SQL
                    generation can continue.
                  </p>
                </div>
              ) : null}
              {previewSubmission.status === "denied" ? (
                <div className="state-callout state-callout-danger" role="status">
                  <p className="state-callout-title">Preview denied</p>
                  <p>
                    Request state {previewSubmission.requestState}; candidate state{" "}
                    {previewSubmission.candidateState}. No successful answer plan is displayed.
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
              {executeSubmission.status === "executing" ? (
                <div className="state-callout state-callout-warning" role="status">
                  <p className="state-callout-title">Execution in progress</p>
                  <p>The reviewed candidate is locked while execute-time checks run.</p>
                </div>
              ) : null}
              {executeSubmission.status === "succeeded" ? (
                <div className="state-callout state-callout-success" role="status">
                  <p className="state-callout-title">Execution completed</p>
                  <p>
                    Candidate {executeSubmission.candidateId} returned {executeSubmission.rowCount}{" "}
                    rows.
                  </p>
                </div>
              ) : null}
              {executeSubmission.status === "denied" ? (
                <div className="state-callout state-callout-danger" role="status">
                  <p className="state-callout-title">Execute denied</p>
                  <p>{executeSubmission.message}</p>
                </div>
              ) : null}
              {executeSubmission.status === "canceled" ? (
                <div className="state-callout" role="status">
                  <p className="state-callout-title">Execution canceled</p>
                  <p>
                    Candidate {executeSubmission.candidateId} did not complete and no successful
                    result payload is shown.
                  </p>
                </div>
              ) : null}
              {executeSubmission.status === "failed" ? (
                <div className="state-callout state-callout-danger" role="alert">
                  <p className="state-callout-title">{executeSubmission.code}</p>
                  <p>{executeSubmission.message}</p>
                </div>
              ) : null}
              <div className="form-actions">
                <button disabled={queryLocked} type="submit">
                  {previewSubmission.status === "submitting"
                    ? "Submitting preview"
                    : "Submit for preview"}
                </button>
                {executeControlVisible ? (
                  <button
                    disabled={!executeEnabled || executeSubmission.status === "executing"}
                    onClick={executeCandidate}
                    type="button"
                  >
                    {executeSubmission.status === "executing"
                      ? "Executing candidate"
                      : "Execute reviewed candidate"}
                  </button>
                ) : null}
                {canOpenCompletedFromPreview &&
                boundSourceId &&
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
          {operatorRecoveryGuidance
            ? renderOperatorRecoveryGuidance(operatorRecoveryGuidance)
            : null}

          <section className="surface surface-secondary">
            <div className="section-header">
              <div>
                <p className="eyebrow">Generated SQL</p>
                <h2 className="panel-title">Technical SQL review</h2>
              </div>
              <span className="surface-badge surface-badge-code">Preview</span>
            </div>
            <div className="state-callout" aria-label="Authorized operator SQL review">
              <p className="state-callout-title">Authorized operator review surface</p>
              <p>
                Raw candidate SQL is visible only inside this authorized operator workflow review.
                Support bundles and handoff exports stay redacted and exclude raw SQL, secrets,
                connection strings, result rows, and local paths.
              </p>
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
              {selectedRevisionContext ? (
                <div className="guard-item">
                  <span className="meta-label">Revised from</span>
                  <strong>
                    {selectedRevisionContext.runId ??
                      selectedRevisionContext.candidateId ??
                      selectedRevisionContext.requestId}
                  </strong>
                </div>
              ) : null}
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
                <strong>
                  {executeEnabled ? "Candidate execute available" : "No executable candidate"}
                </strong>
              </div>
            </div>
          </section>

          {renderAuditEvidencePanel(
            selectedAuditEvents,
            selectedExecutedEvidence,
            selectedRetrievedCitations,
            selectedReviewEvidence,
            operatorWorkflow.history,
            submittedQuestion
          )}

          {renderSupplementalAnalystNarrative(historyRunContext?.analystResponse ?? null)}

          {renderCandidateAttemptComparison(selectedCandidateAttempts)}

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
