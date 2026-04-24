export type AnalystConfidence = "low" | "medium" | "high" | "unknown";
export type SourceFamily = "mssql" | "postgresql";

export type AnalystRetrievalCitation = {
  assetId: string;
  assetKind: string;
  citationLabel: string;
  sourceId: string;
  sourceFamily: SourceFamily;
  sourceFlavor: string | null;
  datasetContractVersion: number;
  schemaSnapshotVersion: number;
  authority: "advisory_context";
  canAuthorizeExecution: false;
};

export type AnalystExecutedEvidence = {
  type: "executed_evidence";
  sourceId: string;
  sourceFamily: SourceFamily;
  sourceFlavor: string | null;
  datasetContractVersion: number;
  schemaSnapshotVersion: number;
  executionPolicyVersion: number | null;
  connectorProfileVersion: number | null;
  candidateId: string;
  executionAuditEventId: string;
  executionAuditEventType: "execution_completed";
  rowCount: number;
  resultTruncated: boolean;
  authority: "backend_execution_result";
  canAuthorizeExecution: false;
};

export type AnalystResponsePayload = {
  responseId: string;
  requestId: string;
  narrative: string;
  advisoryOnly: true;
  canAuthorizeExecution: false;
  analystModeVersion: string;
  confidence: AnalystConfidence;
  caveats: string[];
  retrievalCitations: AnalystRetrievalCitation[];
  executedEvidence: AnalystExecutedEvidence[];
};

type RawObject = Record<string, unknown>;

const sourceIdPattern = /^[a-z0-9][a-z0-9._-]*$/;

function isObject(value: unknown): value is RawObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readRequiredString(value: unknown): string | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }

  return value;
}

function readOptionalString(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }

  return readRequiredString(value);
}

function readSourceId(value: unknown): string | null {
  const sourceId = readRequiredString(value);
  return sourceId !== null && sourceIdPattern.test(sourceId) ? sourceId : null;
}

function readSourceFamily(value: unknown): SourceFamily | null {
  return value === "mssql" || value === "postgresql" ? value : null;
}

function readPositiveInteger(value: unknown): number | null {
  return Number.isInteger(value) && typeof value === "number" && value > 0 ? value : null;
}

function readNonNegativeInteger(value: unknown): number | null {
  return Number.isInteger(value) && typeof value === "number" && value >= 0 ? value : null;
}

function readConfidence(value: unknown): AnalystConfidence | null {
  if (value === "low" || value === "medium" || value === "high" || value === "unknown") {
    return value;
  }

  return null;
}

function parseCaveats(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return [];
  }

  const caveats = value.map(readRequiredString);
  return caveats.every((item): item is string => item !== null) ? caveats : null;
}

function parseRetrievalCitation(value: unknown): AnalystRetrievalCitation | null {
  if (!isObject(value)) {
    return null;
  }

  const assetId = readRequiredString(value.assetId);
  const assetKind = readRequiredString(value.assetKind);
  const citationLabel = readRequiredString(value.citationLabel);
  const sourceId = readSourceId(value.sourceId);
  const sourceFamily = readSourceFamily(value.sourceFamily);
  const sourceFlavor = readOptionalString(value.sourceFlavor);
  const datasetContractVersion = readPositiveInteger(value.datasetContractVersion);
  const schemaSnapshotVersion = readPositiveInteger(value.schemaSnapshotVersion);

  if (
    !assetId ||
    !assetKind ||
    !citationLabel ||
    !sourceId ||
    !sourceFamily ||
    !datasetContractVersion ||
    !schemaSnapshotVersion ||
    value.authority !== "advisory_context" ||
    value.canAuthorizeExecution !== false
  ) {
    return null;
  }

  return {
    assetId,
    assetKind,
    citationLabel,
    sourceId,
    sourceFamily,
    sourceFlavor,
    datasetContractVersion,
    schemaSnapshotVersion,
    authority: "advisory_context",
    canAuthorizeExecution: false
  };
}

function parseExecutedEvidence(value: unknown): AnalystExecutedEvidence | null {
  if (!isObject(value)) {
    return null;
  }

  const sourceId = readSourceId(value.sourceId);
  const sourceFamily = readSourceFamily(value.sourceFamily);
  const sourceFlavor = readOptionalString(value.sourceFlavor);
  const datasetContractVersion = readPositiveInteger(value.datasetContractVersion);
  const schemaSnapshotVersion = readPositiveInteger(value.schemaSnapshotVersion);
  const executionPolicyVersion = readPositiveInteger(value.executionPolicyVersion);
  const connectorProfileVersion = readPositiveInteger(value.connectorProfileVersion);
  const candidateId = readRequiredString(value.candidateId);
  const executionAuditEventId = readRequiredString(value.executionAuditEventId);
  const rowCount = readNonNegativeInteger(value.rowCount);

  if (
    value.type !== "executed_evidence" ||
    !sourceId ||
    !sourceFamily ||
    !datasetContractVersion ||
    !schemaSnapshotVersion ||
    !candidateId ||
    !executionAuditEventId ||
    value.executionAuditEventType !== "execution_completed" ||
    rowCount === null ||
    typeof value.resultTruncated !== "boolean" ||
    value.authority !== "backend_execution_result" ||
    value.canAuthorizeExecution !== false
  ) {
    return null;
  }

  return {
    type: "executed_evidence",
    sourceId,
    sourceFamily,
    sourceFlavor,
    datasetContractVersion,
    schemaSnapshotVersion,
    executionPolicyVersion,
    connectorProfileVersion,
    candidateId,
    executionAuditEventId,
    executionAuditEventType: "execution_completed",
    rowCount,
    resultTruncated: value.resultTruncated,
    authority: "backend_execution_result",
    canAuthorizeExecution: false
  };
}

function parseArray<T>(value: unknown, parser: (item: unknown) => T | null): T[] | null {
  if (!Array.isArray(value)) {
    return [];
  }

  const parsed = value.map(parser);
  return parsed.every((item): item is T => item !== null) ? parsed : null;
}

export function parseAnalystResponsePayload(value: unknown): AnalystResponsePayload | null {
  if (!isObject(value)) {
    return null;
  }

  const responseId = readRequiredString(value.responseId);
  const requestId = readRequiredString(value.requestId);
  const narrative = readRequiredString(value.narrative);
  const analystModeVersion = readRequiredString(value.analystModeVersion);
  const confidence = readConfidence(value.confidence ?? "unknown");
  const caveats = parseCaveats(value.caveats);
  const retrievalCitations = parseArray(value.retrievalCitations, parseRetrievalCitation);
  const executedEvidence = parseArray(value.executedEvidence, parseExecutedEvidence);

  if (
    !responseId ||
    !requestId ||
    !narrative ||
    value.advisoryOnly !== true ||
    value.canAuthorizeExecution !== false ||
    !analystModeVersion ||
    !confidence ||
    caveats === null ||
    retrievalCitations === null ||
    executedEvidence === null ||
    (retrievalCitations.length === 0 && executedEvidence.length === 0)
  ) {
    return null;
  }

  return {
    responseId,
    requestId,
    narrative,
    advisoryOnly: true,
    canAuthorizeExecution: false,
    analystModeVersion,
    confidence,
    caveats,
    retrievalCitations,
    executedEvidence
  };
}
