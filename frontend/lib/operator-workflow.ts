export type SourceActivationPosture = "active" | "paused" | "blocked" | "retired";
export type GovernanceBindingState = "valid" | "missing" | "ambiguous" | "stale" | "drifted";
export type GovernanceBindingRole = "owner" | "security_review" | "exception_policy";

export type GovernanceBindingStatus = {
  affectsEntitlement: boolean;
  recovery: string;
  role: GovernanceBindingRole;
  state: GovernanceBindingState;
  summary: string;
};

export type SourceOption = {
  activationPosture: SourceActivationPosture;
  description: string;
  displayLabel: string;
  governanceBindings: GovernanceBindingStatus[];
  sourceFamily?: string;
  sourceFlavor?: string | null;
  sourceId: string;
};

export type OperatorWorkflowAuditEvent = {
  candidateId: string | null;
  candidateState: string | null;
  eventId: string;
  eventType: string;
  occurredAt: string;
  primaryDenyCode: string | null;
  requestId: string;
  resultTruncated: boolean | null;
  rowCount: number | null;
  sourceId: string;
};

export type OperatorWorkflowExecutedEvidence = {
  authority: "backend_execution_result";
  canAuthorizeExecution: false;
  candidateId: string;
  executionAuditEventId: string;
  executionAuditEventType: "execution_completed";
  rowCount: number;
  resultTruncated: boolean;
  sourceId: string;
  sourceFamily: string;
  sourceFlavor: string | null;
};

export type OperatorWorkflowRetrievedCitation = {
  assetId: string;
  assetKind: string;
  authority: "advisory_context";
  canAuthorizeExecution: false;
  citationLabel: string;
  sourceId: string;
  sourceFamily: string;
  sourceFlavor: string | null;
};

export type OperatorHistoryItem = {
  auditEvents: OperatorWorkflowAuditEvent[];
  candidateSql?: string | null;
  executedEvidence: OperatorWorkflowExecutedEvidence[];
  guardStatus?: string | null;
  itemType: "request" | "candidate" | "run";
  label: string;
  lifecycleState: string;
  occurredAt: string;
  primaryDenyCode?: string | null;
  recordId: string;
  requestId?: string | null;
  resultTruncated?: boolean | null;
  rowCount?: number | null;
  runState?: string | null;
  sourceId: string;
  sourceLabel: string;
  retrievedCitations: OperatorWorkflowRetrievedCitation[];
};

export type OperatorWorkflowSnapshot = {
  error?: {
    code: string;
    message: string;
  };
  history: OperatorHistoryItem[];
  sources: SourceOption[];
  status:
    | "live"
    | "unavailable"
    | "malformed"
    | "unauthenticated"
    | "session_invalid"
    | "csrf_failed"
    | "entitlement_denied";
};

type RawObject = Record<string, unknown>;

function isObject(value: unknown): value is RawObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isActivationPosture(value: unknown): value is SourceActivationPosture {
  return value === "active" || value === "paused" || value === "blocked" || value === "retired";
}

function isGovernanceBindingState(value: unknown): value is GovernanceBindingState {
  return (
    value === "valid" ||
    value === "missing" ||
    value === "ambiguous" ||
    value === "stale" ||
    value === "drifted"
  );
}

function isGovernanceBindingRole(value: unknown): value is GovernanceBindingRole {
  return value === "owner" || value === "security_review" || value === "exception_policy";
}

function readOptionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value : undefined;
}

function readOptionalNonNegativeInteger(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

function parseArray<T>(value: unknown, parser: (item: unknown) => T | null): T[] | null {
  if (value === undefined) {
    return [];
  }

  if (!Array.isArray(value)) {
    return null;
  }

  const parsed = value.map(parser);
  return parsed.every((item): item is T => item !== null) ? parsed : null;
}

function parseAuditEvent(value: unknown): OperatorWorkflowAuditEvent | null {
  if (!isObject(value)) {
    return null;
  }

  const eventId = readOptionalString(value.eventId);
  const eventType = readOptionalString(value.eventType);
  const occurredAt = readOptionalString(value.occurredAt);
  const requestId = readOptionalString(value.requestId);
  const sourceId = readOptionalString(value.sourceId);

  if (!eventId || !eventType || !occurredAt || !requestId || !sourceId) {
    return null;
  }

  return {
    candidateId: readOptionalString(value.candidateId) ?? null,
    candidateState: readOptionalString(value.candidateState) ?? null,
    eventId,
    eventType,
    occurredAt,
    primaryDenyCode: readOptionalString(value.primaryDenyCode) ?? null,
    requestId,
    resultTruncated: typeof value.resultTruncated === "boolean" ? value.resultTruncated : null,
    rowCount: readOptionalNonNegativeInteger(value.rowCount) ?? null,
    sourceId
  };
}

function parseExecutedEvidence(value: unknown): OperatorWorkflowExecutedEvidence | null {
  if (!isObject(value)) {
    return null;
  }

  const candidateId = readOptionalString(value.candidateId);
  const executionAuditEventId = readOptionalString(value.executionAuditEventId);
  const rowCount = readOptionalNonNegativeInteger(value.rowCount);
  const sourceId = readOptionalString(value.sourceId);
  const sourceFamily = readOptionalString(value.sourceFamily);

  if (
    value.authority !== "backend_execution_result" ||
    value.canAuthorizeExecution !== false ||
    !candidateId ||
    !executionAuditEventId ||
    value.executionAuditEventType !== "execution_completed" ||
    rowCount === undefined ||
    typeof value.resultTruncated !== "boolean" ||
    !sourceId ||
    !sourceFamily
  ) {
    return null;
  }

  return {
    authority: "backend_execution_result",
    canAuthorizeExecution: false,
    candidateId,
    executionAuditEventId,
    executionAuditEventType: "execution_completed",
    rowCount,
    resultTruncated: value.resultTruncated,
    sourceId,
    sourceFamily,
    sourceFlavor: readOptionalString(value.sourceFlavor) ?? null
  };
}

function parseRetrievedCitation(value: unknown): OperatorWorkflowRetrievedCitation | null {
  if (!isObject(value)) {
    return null;
  }

  const assetId = readOptionalString(value.assetId);
  const assetKind = readOptionalString(value.assetKind);
  const citationLabel = readOptionalString(value.citationLabel);
  const sourceId = readOptionalString(value.sourceId);
  const sourceFamily = readOptionalString(value.sourceFamily);

  if (
    value.authority !== "advisory_context" ||
    value.canAuthorizeExecution !== false ||
    !assetId ||
    !assetKind ||
    !citationLabel ||
    !sourceId ||
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
    sourceId,
    sourceFamily,
    sourceFlavor: readOptionalString(value.sourceFlavor) ?? null
  };
}

function parseGovernanceBindingStatus(value: unknown): GovernanceBindingStatus | null {
  if (!isObject(value)) {
    return null;
  }

  const summary = readOptionalString(value.summary);
  const recovery = readOptionalString(value.recovery);
  if (
    !isGovernanceBindingRole(value.role) ||
    !isGovernanceBindingState(value.state) ||
    typeof value.affectsEntitlement !== "boolean" ||
    !summary ||
    !recovery
  ) {
    return null;
  }

  return {
    affectsEntitlement: value.affectsEntitlement,
    recovery,
    role: value.role,
    state: value.state,
    summary
  };
}

function parseSourceOption(value: unknown): SourceOption | null {
  if (!isObject(value)) {
    return null;
  }

  const sourceId = readOptionalString(value.sourceId);
  const displayLabel = readOptionalString(value.displayLabel);
  const description = readOptionalString(value.description);
  const governanceBindings = Array.isArray(value.governanceBindings)
    ? parseArray(value.governanceBindings, parseGovernanceBindingStatus)
    : null;

  if (
    !sourceId ||
    !displayLabel ||
    !description ||
    !isActivationPosture(value.activationPosture) ||
    governanceBindings === null
  ) {
    return null;
  }

  return {
    activationPosture: value.activationPosture,
    description,
    displayLabel,
    governanceBindings,
    sourceFamily: readOptionalString(value.sourceFamily),
    sourceFlavor: readOptionalString(value.sourceFlavor) ?? null,
    sourceId
  };
}

function parseHistoryItem(value: unknown): OperatorHistoryItem | null {
  if (!isObject(value)) {
    return null;
  }

  const itemType = value.itemType;
  const recordId = readOptionalString(value.recordId);
  const label = readOptionalString(value.label);
  const sourceId = readOptionalString(value.sourceId);
  const sourceLabel = readOptionalString(value.sourceLabel);
  const lifecycleState = readOptionalString(value.lifecycleState);
  const occurredAt = readOptionalString(value.occurredAt);
  const auditEvents = parseArray(value.auditEvents, parseAuditEvent);
  const executedEvidence = parseArray(value.executedEvidence, parseExecutedEvidence);
  const retrievedCitations = parseArray(value.retrievedCitations, parseRetrievedCitation);

  if (
    (itemType !== "request" && itemType !== "candidate" && itemType !== "run") ||
    !recordId ||
    !label ||
    !sourceId ||
    !sourceLabel ||
    !lifecycleState ||
    !occurredAt ||
    auditEvents === null ||
    executedEvidence === null ||
    retrievedCitations === null
  ) {
    return null;
  }

  return {
    auditEvents,
    candidateSql: readOptionalString(value.candidateSql) ?? null,
    executedEvidence,
    guardStatus: readOptionalString(value.guardStatus) ?? null,
    itemType,
    label,
    lifecycleState,
    occurredAt,
    primaryDenyCode: readOptionalString(value.primaryDenyCode) ?? null,
    recordId,
    requestId: readOptionalString(value.requestId) ?? null,
    resultTruncated:
      typeof value.resultTruncated === "boolean" ? value.resultTruncated : null,
    rowCount: readOptionalNonNegativeInteger(value.rowCount) ?? null,
    runState: readOptionalString(value.runState) ?? null,
    sourceId,
    sourceLabel,
    retrievedCitations
  };
}

function unavailableSnapshot(status: OperatorWorkflowSnapshot["status"]): OperatorWorkflowSnapshot {
  return {
    history: [],
    sources: [],
    status
  };
}

function parseApiError(value: unknown): OperatorWorkflowSnapshot["error"] | undefined {
  if (!isObject(value) || !isObject(value.error)) {
    return undefined;
  }

  const code = readOptionalString(value.error.code);
  const message = readOptionalString(value.error.message);
  if (!code || !message) {
    return undefined;
  }

  return { code, message };
}

function unavailableSnapshotForApiError(payload: unknown): OperatorWorkflowSnapshot {
  const error = parseApiError(payload);
  if (
    error?.code === "unauthenticated" ||
    error?.code === "session_invalid" ||
    error?.code === "csrf_failed" ||
    error?.code === "entitlement_denied"
  ) {
    return {
      ...unavailableSnapshot(error.code),
      error
    };
  }

  return unavailableSnapshot("unavailable");
}

function isParsedSourceOption(value: SourceOption | null): value is SourceOption {
  return value !== null;
}

function isParsedHistoryItem(value: OperatorHistoryItem | null): value is OperatorHistoryItem {
  return value !== null;
}

export async function getOperatorWorkflowSnapshot(
  apiInternalBaseUrl: string
): Promise<OperatorWorkflowSnapshot> {
  try {
    const response = await fetch(`${apiInternalBaseUrl}/operator/workflow`, {
      cache: "no-store"
    });

    if (!response.ok) {
      let payload: unknown;
      try {
        payload = (await response.json()) as unknown;
      } catch {
        return unavailableSnapshot("unavailable");
      }

      return unavailableSnapshotForApiError(payload);
    }

    let payload: unknown;
    try {
      payload = (await response.json()) as unknown;
    } catch {
      return unavailableSnapshot("malformed");
    }

    if (!isObject(payload) || !Array.isArray(payload.sources) || !Array.isArray(payload.history)) {
      return unavailableSnapshot("malformed");
    }

    const sources = payload.sources.map(parseSourceOption);
    const history = payload.history.map(parseHistoryItem);

    if (!sources.every(isParsedSourceOption) || !history.every(isParsedHistoryItem)) {
      return unavailableSnapshot("malformed");
    }

    return {
      history,
      sources,
      status: "live"
    };
  } catch {
    return unavailableSnapshot("unavailable");
  }
}
