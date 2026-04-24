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
    executionAuditEventId: "5dbcc36c-c6d6-4755-b307-5a3af5d6ec25",
    executionAuditEventType: "execution_completed",
    rowCount: 12,
    resultTruncated: false,
    authority: "backend_execution_result",
    canAuthorizeExecution: false
  };
}

describe("parseAnalystResponsePayload", () => {
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
});
