export type SourceActivationPosture = "active" | "paused" | "blocked" | "retired";

export type SourceOption = {
  activationPosture: SourceActivationPosture;
  description: string;
  displayLabel: string;
  sourceFamily?: string;
  sourceFlavor?: string | null;
  sourceId: string;
};

export type OperatorHistoryItem = {
  candidateSql?: string | null;
  guardStatus?: string | null;
  itemType: "request" | "candidate" | "run";
  label: string;
  lifecycleState: string;
  occurredAt: string;
  recordId: string;
  requestId?: string | null;
  runState?: string | null;
  sourceId: string;
  sourceLabel: string;
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

function readOptionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value : undefined;
}

function parseSourceOption(value: unknown): SourceOption | null {
  if (!isObject(value)) {
    return null;
  }

  const sourceId = readOptionalString(value.sourceId);
  const displayLabel = readOptionalString(value.displayLabel);
  const description = readOptionalString(value.description);

  if (!sourceId || !displayLabel || !description || !isActivationPosture(value.activationPosture)) {
    return null;
  }

  return {
    activationPosture: value.activationPosture,
    description,
    displayLabel,
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

  if (
    (itemType !== "request" && itemType !== "candidate" && itemType !== "run") ||
    !recordId ||
    !label ||
    !sourceId ||
    !sourceLabel ||
    !lifecycleState ||
    !occurredAt
  ) {
    return null;
  }

  return {
    candidateSql: readOptionalString(value.candidateSql) ?? null,
    guardStatus: readOptionalString(value.guardStatus) ?? null,
    itemType,
    label,
    lifecycleState,
    occurredAt,
    recordId,
    requestId: readOptionalString(value.requestId) ?? null,
    runState: readOptionalString(value.runState) ?? null,
    sourceId,
    sourceLabel
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
