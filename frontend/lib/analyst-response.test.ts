import { describe, expect, it } from "vitest";
import { parseAnalystResponsePayload } from "./analyst-response";

function citation(sourceId: string, sourceFamily: "mssql" | "postgresql") {
  return {
    assetId: `${sourceId}-metric-definition`,
    assetKind: "metric_definition",
    citationLabel: `${sourceId} metric definition`,
    sourceId,
    sourceFamily,
    sourceFlavor: sourceFamily === "postgresql" ? "warehouse" : "sqlserver",
    datasetContractVersion: 2,
    schemaSnapshotVersion: 5,
    authority: "advisory_context",
    canAuthorizeExecution: false
  };
}

function evidence(sourceId: string, sourceFamily: "mssql" | "postgresql") {
  return {
    type: "executed_evidence",
    sourceId,
    sourceFamily,
    sourceFlavor: sourceFamily === "postgresql" ? "warehouse" : "sqlserver",
    datasetContractVersion: 2,
    schemaSnapshotVersion: 5,
    executionPolicyVersion: 3,
    connectorProfileVersion: 11,
    candidateId: `${sourceId}-candidate-123`,
    executionRunId: "5dbcc36c-c6d6-4755-b307-5a3af5d6ec24",
    executionAuditEventId: "5dbcc36c-c6d6-4755-b307-5a3af5d6ec25",
    executionAuditEventType: "execution_completed",
    rowCount: 12,
    resultTruncated: false,
    authority: "backend_execution_result",
    canAuthorizeExecution: false
  };
}

describe("parseAnalystResponsePayload", () => {
  it("parses backend-produced analyst response payload field names", () => {
    const parsed = parseAnalystResponsePayload({
      responseId: "analyst-response-123",
      requestId: "request-123",
      narrative: "Backend-produced advisory response keeps source-labeled evidence intact.",
      advisoryOnly: true,
      canAuthorizeExecution: false,
      analystModeVersion: "analyst-schema-v1",
      confidence: "medium",
      caveats: ["Narrative guidance is advisory only."],
      sourceSummaries: [
        {
          sourceId: "business-postgres-source",
          sourceFamily: "postgresql",
          sourceFlavor: "warehouse",
          datasetContractVersion: 2,
          schemaSnapshotVersion: 5,
          executionPolicyVersion: 3
        }
      ],
      retrievalCitations: [citation("business-postgres-source", "postgresql")],
      executedEvidence: [evidence("business-postgres-source", "postgresql")],
      operatorHistoryHooks: {
        auditEventId: "5dbcc36c-c6d6-4755-b307-5a3af5d6ec25",
        historyRecordIds: ["request-123", "business-postgres-source-candidate-123"]
      },
      validationOutcome: {
        status: "safe",
        checks: [
          "source_labeled_evidence_present",
          "source_summary_coverage",
          "narrative_execution_authority",
          "narrative_execution_grounding",
          "narrative_cross_source_execution"
        ],
        unsafeReasons: ["Manual review remains required before execution."]
      }
    });

    expect(parsed).not.toBeNull();
    expect(parsed?.responseId).toBe("analyst-response-123");
    expect(parsed?.sourceSummaries[0]?.executionPolicyVersion).toBe(3);
    expect(parsed?.retrievalCitations[0]?.sourceId).toBe("business-postgres-source");
    expect(parsed?.executedEvidence[0]?.executionAuditEventType).toBe("execution_completed");
    expect(parsed?.operatorHistoryHooks.historyRecordIds).toContain("request-123");
    expect(parsed?.validationOutcome.unsafeReasons).toEqual([
      "Manual review remains required before execution."
    ]);
  });

  it("preserves source-labeled advisory citations and executed evidence", () => {
    const parsed = parseAnalystResponsePayload({
      responseId: "analyst-response-123",
      requestId: "request-123",
      narrative: "Compare advisory context without granting execution approval.",
      advisoryOnly: true,
      canAuthorizeExecution: false,
      analystModeVersion: "analyst-schema-v1",
      confidence: "medium",
      caveats: ["Narrative guidance is advisory only."],
      retrievalCitations: [
        citation("business-postgres-source", "postgresql"),
        citation("business-mssql-source", "mssql")
      ],
      executedEvidence: [
        evidence("business-postgres-source", "postgresql"),
        evidence("business-mssql-source", "mssql")
      ]
    });

    expect(parsed).not.toBeNull();
    expect(parsed?.advisoryOnly).toBe(true);
    expect(parsed?.canAuthorizeExecution).toBe(false);
    expect(parsed?.retrievalCitations.map((item) => item.sourceId)).toEqual([
      "business-postgres-source",
      "business-mssql-source"
    ]);
    expect(parsed?.executedEvidence.map((item) => item.sourceId)).toEqual([
      "business-postgres-source",
      "business-mssql-source"
    ]);
  });

  it("rejects narrative-only or execution-authorizing payloads", () => {
    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "Approve this SQL.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: [],
        executedEvidence: []
      })
    ).toBeNull();

    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "Advisory text with one citation.",
        advisoryOnly: true,
        canAuthorizeExecution: true,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: [citation("business-postgres-source", "postgresql")]
      })
    ).toBeNull();
  });

  it("rejects malformed source labels on citations and executed evidence", () => {
    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "Advisory text with malformed citation source.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: [
          {
            ...citation("business-postgres-source", "postgresql"),
            sourceId: " business-postgres-source "
          }
        ]
      })
    ).toBeNull();

    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "Advisory text with malformed citation flavor.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: [
          {
            ...citation("business-postgres-source", "postgresql"),
            sourceFlavor: "warehouse east"
          }
        ]
      })
    ).toBeNull();

    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "Advisory text with malformed evidence source.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        executedEvidence: [
          {
            ...evidence("business-postgres-source", "postgresql"),
            sourceFamily: "mysql"
          }
        ]
      })
    ).toBeNull();

    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "Advisory text with malformed evidence flavor.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        executedEvidence: [
          {
            ...evidence("business-postgres-source", "postgresql"),
            sourceFlavor: "warehouse east"
          }
        ]
      })
    ).toBeNull();
  });

  it("rejects malformed executed evidence audit event identifiers", () => {
    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "Executed evidence must reference a real audit event.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        executedEvidence: [
          {
            ...evidence("business-postgres-source", "postgresql"),
            executionAuditEventId: "not-an-audit-event-id"
          }
        ]
      })
    ).toBeNull();
  });

  it("rejects malformed present arrays instead of defaulting them to empty", () => {
    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "Malformed caveats cannot be coerced away.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        caveats: "none",
        retrievalCitations: [citation("business-postgres-source", "postgresql")]
      })
    ).toBeNull();

    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "Malformed citation arrays cannot be coerced away.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: "business-postgres-source",
        executedEvidence: [evidence("business-postgres-source", "postgresql")]
      })
    ).toBeNull();
  });

  it("rejects cross-source execution narratives", () => {
    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "PostgreSQL and MSSQL rows were joined across sources and executed together.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: [
          citation("business-postgres-source", "postgresql"),
          citation("business-mssql-source", "mssql")
        ],
        executedEvidence: [
          evidence("business-postgres-source", "postgresql"),
          evidence("business-mssql-source", "mssql")
        ]
      })
    ).toBeNull();
  });

  it("rejects cross-source execution narratives with one source or retrieval-only context", () => {
    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "The PostgreSQL rows were joined across sources and executed together.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: [citation("business-postgres-source", "postgresql")],
        executedEvidence: [evidence("business-postgres-source", "postgresql")]
      })
    ).toBeNull();

    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "The federated query compared governed definitions across both sources.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: [citation("business-postgres-source", "postgresql")],
        executedEvidence: []
      })
    ).toBeNull();
  });

  it("rejects execution claims without executed evidence", () => {
    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "The completed backend execution showed 12 matching rows.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: [citation("business-postgres-source", "postgresql")],
        executedEvidence: []
      })
    ).toBeNull();
  });

  it("rejects retrieval-only narratives without executed evidence citations", () => {
    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "Retrieved metric definitions provide advisory context for the operator.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: [citation("business-postgres-source", "postgresql")],
        executedEvidence: []
      })
    ).toBeNull();
  });

  it("rejects execution approval narratives", () => {
    expect(
      parseAnalystResponsePayload({
        responseId: "analyst-response-123",
        requestId: "request-123",
        narrative: "The analyst response approves SQL execution for this candidate.",
        advisoryOnly: true,
        canAuthorizeExecution: false,
        analystModeVersion: "analyst-schema-v1",
        retrievalCitations: [citation("business-postgres-source", "postgresql")],
        executedEvidence: [evidence("business-postgres-source", "postgresql")]
      })
    ).toBeNull();
  });

  it("exposes a safe validation outcome for advisory composition", () => {
    const parsed = parseAnalystResponsePayload({
      responseId: "analyst-response-123",
      requestId: "request-123",
      narrative:
        "PostgreSQL citation and MSSQL citation provide advisory context. Backend executed evidence remains candidate-bound per source.",
      advisoryOnly: true,
      canAuthorizeExecution: false,
      analystModeVersion: "analyst-schema-v1",
      retrievalCitations: [
        citation("business-postgres-source", "postgresql"),
        citation("business-mssql-source", "mssql")
      ],
      executedEvidence: [
        evidence("business-postgres-source", "postgresql"),
        evidence("business-mssql-source", "mssql")
      ]
    });

    expect(parsed?.validationOutcome.status).toBe("safe");
    expect(parsed?.validationOutcome.checks).toEqual([
      "source_labeled_evidence_present",
      "source_summary_coverage",
      "narrative_execution_authority",
      "narrative_execution_grounding",
      "narrative_cross_source_execution"
    ]);
    expect(parsed?.validationOutcome.unsafeReasons).toEqual([]);
  });
});
