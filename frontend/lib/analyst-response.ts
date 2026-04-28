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
  executionRunId: string;
  executionAuditEventId: string;
  executionAuditEventType: "execution_completed";
  rowCount: number;
  resultTruncated: boolean;
  authority: "backend_execution_result";
  canAuthorizeExecution: false;
};

export type AnalystSourceSummary = {
  sourceId: string;
  sourceFamily: SourceFamily;
  sourceFlavor: string | null;
  datasetContractVersion: number;
  schemaSnapshotVersion: number;
  executionPolicyVersion: number | null;
};

export type AnalystOperatorHistoryHooks = {
  auditEventId: string | null;
  historyRecordIds: string[];
};

export type AnalystValidationOutcome = {
  status: "safe";
  checks: [
    "source_labeled_evidence_present",
    "source_summary_coverage",
    "narrative_execution_authority",
    "narrative_execution_grounding",
    "narrative_cross_source_execution"
  ];
  unsafeReasons: string[];
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
  sourceSummaries: AnalystSourceSummary[];
  retrievalCitations: AnalystRetrievalCitation[];
  executedEvidence: AnalystExecutedEvidence[];
  operatorHistoryHooks: AnalystOperatorHistoryHooks;
  validationOutcome: AnalystValidationOutcome;
};

type RawObject = Record<string, unknown>;

const sourceTokenPattern = /^[a-z0-9][a-z0-9._-]*$/;
const executionAuditEventIdPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const executionApprovalPattern =
  /\b(approv(?:e|es|ed|ing)\s+(?:sql\s+)?execution|execution\s+(?:is\s+)?approv(?:e|ed)|authori[sz](?:e|es|ed|ing)\s+(?:sql\s+)?execution|execution\s+(?:is\s+)?authori[sz](?:e|ed)|safe\s+to\s+(?:execute|run)|can\s+(?:execute|run)\s+(?:this\s+)?(?:sql|query|candidate))\b/i;
const executionClaimPattern =
  /\b(backend\s+execution\s+(?:show(?:s|ed)?|returned|produced)|completed\s+backend\s+execution|execut(?:e|ed|ion)\s+(?:result|evidence)\s+(?:show(?:s|ed)?|returned|produced)|(?:query|candidate)\s+(?:ran|executed)\b|rows?\s+(?:were\s+)?returned)/i;
const crossSourceExecutionPattern =
  /\b(cross[- ]source\s+(?:execution|query|join)|federated\s+(?:execution|query)|(?:joined|merged|combined)\s+(?:across\s+sources|execution\s+results)|executed\s+together|ran\s+across\s+(?:both|multiple)\s+sources)\b/i;

function isObject(value: unknown): value is RawObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readRequiredString(value: unknown): string | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }

  return value;
}

function readSourceToken(value: unknown): string | null {
  const token = readRequiredString(value);
  return token !== null && sourceTokenPattern.test(token) ? token : null;
}

function readOptionalSourceToken(value: unknown): string | null | undefined {
  if (value === null || value === undefined) {
    return null;
  }

  return readSourceToken(value) ?? undefined;
}

function readExecutionAuditEventId(value: unknown): string | null {
  const eventId = readRequiredString(value);
  return eventId !== null && executionAuditEventIdPattern.test(eventId) ? eventId : null;
}

function readOptionalAuditEventId(value: unknown): string | null | undefined {
  if (value === null || value === undefined) {
    return null;
  }

  return readExecutionAuditEventId(value) ?? undefined;
}

function readSourceFamily(value: unknown): SourceFamily | null {
  return value === "mssql" || value === "postgresql" ? value : null;
}

function readPositiveInteger(value: unknown): number | null {
  return Number.isInteger(value) && typeof value === "number" && value > 0 ? value : null;
}

function readOptionalPositiveInteger(value: unknown): number | null | undefined {
  if (value === null || value === undefined) {
    return null;
  }

  return readPositiveInteger(value) ?? undefined;
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
  if (value === undefined) {
    return [];
  }

  if (!Array.isArray(value)) {
    return null;
  }

  const caveats = value.map(readRequiredString);
  return caveats.every((item): item is string => item !== null) ? caveats : null;
}

function parseStringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return null;
  }

  const parsed = value.map(readRequiredString);
  return parsed.every((item): item is string => item !== null) ? parsed : null;
}

function parseSourceSummary(value: unknown): AnalystSourceSummary | null {
  if (!isObject(value)) {
    return null;
  }

  const sourceId = readSourceToken(value.sourceId);
  const sourceFamily = readSourceFamily(value.sourceFamily);
  const sourceFlavor = readOptionalSourceToken(value.sourceFlavor);
  const datasetContractVersion = readPositiveInteger(value.datasetContractVersion);
  const schemaSnapshotVersion = readPositiveInteger(value.schemaSnapshotVersion);
  const executionPolicyVersion = readOptionalPositiveInteger(value.executionPolicyVersion);

  if (
    !sourceId ||
    !sourceFamily ||
    sourceFlavor === undefined ||
    !datasetContractVersion ||
    !schemaSnapshotVersion ||
    executionPolicyVersion === undefined
  ) {
    return null;
  }

  return {
    sourceId,
    sourceFamily,
    sourceFlavor,
    datasetContractVersion,
    schemaSnapshotVersion,
    executionPolicyVersion
  };
}

function parseRetrievalCitation(value: unknown): AnalystRetrievalCitation | null {
  if (!isObject(value)) {
    return null;
  }

  const assetId = readRequiredString(value.assetId);
  const assetKind = readRequiredString(value.assetKind);
  const citationLabel = readRequiredString(value.citationLabel);
  const sourceId = readSourceToken(value.sourceId);
  const sourceFamily = readSourceFamily(value.sourceFamily);
  const sourceFlavor = readOptionalSourceToken(value.sourceFlavor);
  const datasetContractVersion = readPositiveInteger(value.datasetContractVersion);
  const schemaSnapshotVersion = readPositiveInteger(value.schemaSnapshotVersion);

  if (
    !assetId ||
    !assetKind ||
    !citationLabel ||
    !sourceId ||
    !sourceFamily ||
    sourceFlavor === undefined ||
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

  const sourceId = readSourceToken(value.sourceId);
  const sourceFamily = readSourceFamily(value.sourceFamily);
  const sourceFlavor = readOptionalSourceToken(value.sourceFlavor);
  const datasetContractVersion = readPositiveInteger(value.datasetContractVersion);
  const schemaSnapshotVersion = readPositiveInteger(value.schemaSnapshotVersion);
  const executionPolicyVersion = readOptionalPositiveInteger(value.executionPolicyVersion);
  const connectorProfileVersion = readOptionalPositiveInteger(value.connectorProfileVersion);
  const candidateId = readRequiredString(value.candidateId);
  const executionRunId = readExecutionAuditEventId(value.executionRunId);
  const executionAuditEventId = readExecutionAuditEventId(value.executionAuditEventId);
  const rowCount = readNonNegativeInteger(value.rowCount);

  if (
    value.type !== "executed_evidence" ||
    !sourceId ||
    !sourceFamily ||
    sourceFlavor === undefined ||
    !datasetContractVersion ||
    !schemaSnapshotVersion ||
    executionPolicyVersion === undefined ||
    connectorProfileVersion === undefined ||
    !candidateId ||
    !executionRunId ||
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
    executionRunId,
    executionAuditEventId,
    executionAuditEventType: "execution_completed",
    rowCount,
    resultTruncated: value.resultTruncated,
    authority: "backend_execution_result",
    canAuthorizeExecution: false
  };
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

function parseOperatorHistoryHooks(value: unknown): AnalystOperatorHistoryHooks | null {
  if (value === undefined) {
    return {
      auditEventId: null,
      historyRecordIds: []
    };
  }

  if (!isObject(value)) {
    return null;
  }

  const auditEventId = readOptionalAuditEventId(value.auditEventId);
  const historyRecordIds = parseStringArray(value.historyRecordIds);

  if (auditEventId === undefined || historyRecordIds === null) {
    return null;
  }

  return {
    auditEventId,
    historyRecordIds
  };
}

function validateNarrativeAuthority(
  narrative: string,
  retrievalCitations: AnalystRetrievalCitation[],
  executedEvidence: AnalystExecutedEvidence[]
): boolean {
  if (crossSourceExecutionPattern.test(narrative)) {
    return false;
  }

  if (executionApprovalPattern.test(narrative)) {
    return false;
  }

  if (executedEvidence.length === 0 && executionClaimPattern.test(narrative)) {
    return false;
  }

  return true;
}

function defaultValidationOutcome(): AnalystValidationOutcome {
  return {
    status: "safe",
    checks: [
      "source_labeled_evidence_present",
      "source_summary_coverage",
      "narrative_execution_authority",
      "narrative_execution_grounding",
      "narrative_cross_source_execution"
    ],
    unsafeReasons: []
  };
}

function parseValidationOutcome(value: unknown): AnalystValidationOutcome | null {
  if (value === undefined) {
    return defaultValidationOutcome();
  }

  if (!isObject(value)) {
    return null;
  }

  const expectedChecks: AnalystValidationOutcome["checks"] = [
    "source_labeled_evidence_present",
    "source_summary_coverage",
    "narrative_execution_authority",
    "narrative_execution_grounding",
    "narrative_cross_source_execution"
  ];
  const checks = Array.isArray(value.checks) ? value.checks : null;
  const unsafeReasons = parseStringArray(value.unsafeReasons);

  if (
    value.status !== "safe" ||
    checks === null ||
    checks.length !== expectedChecks.length ||
    !expectedChecks.every((check, index) => checks[index] === check) ||
    unsafeReasons === null
  ) {
    return null;
  }

  return {
    status: "safe",
    checks: expectedChecks,
    unsafeReasons
  };
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
  const sourceSummaries = parseArray(value.sourceSummaries, parseSourceSummary);
  const retrievalCitations = parseArray(value.retrievalCitations, parseRetrievalCitation);
  const executedEvidence = parseArray(value.executedEvidence, parseExecutedEvidence);
  const operatorHistoryHooks = parseOperatorHistoryHooks(value.operatorHistoryHooks);
  const validationOutcome = parseValidationOutcome(value.validationOutcome);

  if (
    !responseId ||
    !requestId ||
    !narrative ||
    value.advisoryOnly !== true ||
    value.canAuthorizeExecution !== false ||
    !analystModeVersion ||
    !confidence ||
    caveats === null ||
    sourceSummaries === null ||
    retrievalCitations === null ||
    executedEvidence === null ||
    operatorHistoryHooks === null ||
    validationOutcome === null ||
    (retrievalCitations.length === 0 && executedEvidence.length === 0) ||
    !validateNarrativeAuthority(narrative, retrievalCitations, executedEvidence)
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
    sourceSummaries,
    retrievalCitations,
    executedEvidence,
    operatorHistoryHooks,
    validationOutcome
  };
}
