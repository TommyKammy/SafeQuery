import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HomePage from "./page";

function pilotWorkflowPayload() {
  return {
    history: [
      {
        auditEvents: [
          {
            candidateId: "candidate-pilot-001",
            candidateState: "preview_ready",
            eventId: "audit-preview-001",
            eventType: "guard_evaluated",
            occurredAt: "2026-04-21T14:24:00Z",
            primaryDenyCode: null,
            requestId: "request-pilot-001",
            resultTruncated: null,
            rowCount: null,
            sourceId: "demo-business-postgres"
          }
        ],
        candidateSql: "select vendor_name from finance.approved_vendor_spend limit 10;",
        executedEvidence: [],
        guardStatus: "passed",
        itemType: "candidate",
        label: "Pilot source preview",
        lifecycleState: "preview_ready",
        occurredAt: "2026-04-21T14:24:00Z",
        recordId: "candidate-pilot-001",
        requestId: "request-pilot-001",
        retrievedCitations: [
          {
            assetId: "schema-snapshot-7",
            assetKind: "schema_snapshot",
            authority: "advisory_context",
            canAuthorizeExecution: false,
            citationLabel: "Approved spend schema snapshot",
            sourceFamily: "postgresql",
            sourceFlavor: "warehouse",
            sourceId: "demo-business-postgres"
          }
        ],
        sourceId: "demo-business-postgres",
        sourceLabel: "Demo business PostgreSQL / approved_vendor_spend"
      },
      {
        auditEvents: [
          {
            candidateId: "candidate-pilot-001",
            candidateState: "executed",
            eventId: "run-pilot-001",
            eventType: "execution_completed",
            occurredAt: "2026-04-21T14:32:00Z",
            primaryDenyCode: null,
            requestId: "request-pilot-001",
            resultTruncated: false,
            rowCount: 2,
            sourceId: "demo-business-postgres"
          }
        ],
        executedEvidence: [
          {
            authority: "backend_execution_result",
            canAuthorizeExecution: false,
            candidateId: "candidate-pilot-001",
            executionAuditEventId: "run-pilot-001",
            executionAuditEventType: "execution_completed",
            resultTruncated: false,
            rowCount: 2,
            sourceFamily: "postgresql",
            sourceFlavor: "warehouse",
            sourceId: "demo-business-postgres"
          }
        ],
        itemType: "run",
        label: "Pilot completed run",
        lifecycleState: "completed",
        occurredAt: "2026-04-21T14:32:00Z",
        recordId: "run-pilot-001",
        requestId: "request-pilot-001",
        resultTruncated: false,
        retrievedCitations: [],
        rowCount: 2,
        runState: "completed",
        sourceId: "demo-business-postgres",
        sourceLabel: "Demo business PostgreSQL / approved_vendor_spend"
      }
    ],
    sources: [
      {
        activationPosture: "active",
        description: "Pilot source returned by the backend workflow contract.",
        displayLabel: "Demo business PostgreSQL / approved_vendor_spend",
        governanceBindings: [],
        sourceFamily: "postgresql",
        sourceFlavor: "warehouse",
        sourceId: "demo-business-postgres"
      }
    ]
  };
}

describe("pilot safety UI smoke", () => {
  beforeEach(() => {
    process.env.API_INTERNAL_BASE_URL = "http://127.0.0.1:8000";
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(pilotWorkflowPayload())
          });
        }

        return new Promise(() => {});
      })
    );
  });

  afterEach(() => {
    cleanup();
    document.head.querySelectorAll('meta[name="safequery-csrf-token"]').forEach((node) => {
      node.remove();
    });
    vi.unstubAllGlobals();
  });

  it("renders source-bound preview, result, and audit evidence without placeholder workflow output", async () => {
    render(
      await HomePage({
        searchParams: {
          history_item_type: "candidate",
          history_record_id: "candidate-pilot-001",
          question: "Pilot source preview",
          source_id: "demo-business-postgres",
          state: "preview"
        }
      })
    );

    expect(screen.getByRole("heading", { name: /sql preview state/i })).toBeInTheDocument();
    expect(
      screen.getByText("select vendor_name from finance.approved_vendor_spend limit 10;")
    ).toBeInTheDocument();
    expect(screen.getByText("candidate-pilot-001")).toBeInTheDocument();
    expect(screen.getByLabelText(/audit lifecycle events/i)).toHaveTextContent("guard_evaluated");
    expect(screen.getByLabelText(/retrieved citation context/i)).toHaveTextContent(
      "Approved spend schema snapshot"
    );
    expect(screen.queryByText(/placeholder sql generated/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/placeholder query results/i)).not.toBeInTheDocument();

    cleanup();

    render(
      await HomePage({
        searchParams: {
          history_item_type: "run",
          history_record_id: "run-pilot-001",
          question: "Pilot completed run",
          source_id: "demo-business-postgres",
          state: "completed"
        }
      })
    );

    expect(screen.getByRole("heading", { name: /completed state/i })).toBeInTheDocument();
    expect(screen.getByText(/2 rows returned; result payload not truncated/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/executed evidence/i)).toHaveTextContent("backend_execution_result");
    expect(screen.queryByText(/execution results unavailable/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/placeholder query results/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/run-sq-204/i)).not.toBeInTheDocument();
  });

  it("keeps denied preview and canceled execution on non-success workflow states", async () => {
    const csrfToken = document.createElement("meta");
    csrfToken.name = "safequery-csrf-token";
    csrfToken.content = "csrf-from-session-bootstrap";
    document.head.appendChild(csrfToken);

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = input.toString();

      if (url.endsWith("/operator/workflow")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(pilotWorkflowPayload())
        });
      }

      if (url.endsWith("/requests/preview")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              audit: {
                events: [],
                source_id: "demo-business-postgres",
                state: "recorded"
              },
              candidate: {
                candidate_id: "candidate-denied-001",
                candidate_sql: null,
                guard_status: "blocked",
                source_id: "demo-business-postgres",
                state: "denied"
              },
              request: {
                question: "Delete the spend table",
                request_id: "request-denied-001",
                source_id: "demo-business-postgres",
                state: "blocked"
              }
            })
        });
      }

      if (url.endsWith("/candidates/candidate-pilot-001/execute")) {
        return Promise.resolve({
          ok: false,
          status: 503,
          json: () =>
            Promise.resolve({
              audit: {
                events: [
                  {
                    candidate_state: "canceled",
                    event_type: "execution_failed",
                    query_candidate_id: "candidate-pilot-001"
                  }
                ]
              },
              error: {
                code: "execution_unavailable",
                message: "Candidate execution is unavailable."
              }
            })
        });
      }

      return new Promise(() => {});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(await HomePage({}));

    fireEvent.change(screen.getByRole("combobox", { name: /source/i }), {
      target: { value: "demo-business-postgres" }
    });
    fireEvent.change(screen.getByLabelText(/natural-language question/i), {
      target: { value: "Delete the spend table" }
    });
    fireEvent.submit(screen.getByRole("button", { name: /submit for preview/i }).closest("form")!);

    expect(await screen.findByText(/preview denied/i)).toBeInTheDocument();
    expect(screen.queryByText(/preview request accepted/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /sql preview state/i })).not.toBeInTheDocument();

    cleanup();
    document.head.appendChild(csrfToken);

    render(
      await HomePage({
        searchParams: {
          history_item_type: "candidate",
          history_record_id: "candidate-pilot-001",
          question: "Pilot source preview",
          source_id: "demo-business-postgres",
          state: "preview"
        }
      })
    );

    fireEvent.click(screen.getByRole("button", { name: /execute reviewed candidate/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/candidates/candidate-pilot-001/execute",
        expect.objectContaining({
          body: JSON.stringify({
            selected_source_id: "demo-business-postgres"
          }),
          method: "POST"
        })
      );
    });
    expect(screen.getAllByText(/execution canceled/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: /canceled state/i })).toBeInTheDocument();
    expect(screen.queryByText(/execution completed/i)).not.toBeInTheDocument();
    expect(within(screen.getByLabelText(/operator history/i)).getByText("Pilot completed run")).toBeInTheDocument();
  });

  it("submits a revised preview attempt with prior run context", async () => {
    const csrfToken = document.createElement("meta");
    csrfToken.name = "safequery-csrf-token";
    csrfToken.content = "csrf-from-session-bootstrap";
    document.head.appendChild(csrfToken);

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();

      if (url.endsWith("/operator/workflow")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(pilotWorkflowPayload())
        });
      }

      if (url.endsWith("/requests/preview")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              audit: {
                events: [],
                source_id: "demo-business-postgres",
                state: "recorded"
              },
              candidate: {
                candidate_id: "candidate-revised-001",
                candidate_sql: null,
                guard_status: "pending",
                source_id: "demo-business-postgres",
                state: "preview_ready"
              },
              request: {
                question: "Pilot source preview with revised filter",
                request_id: "request-revised-001",
                revision_context: {
                  run_id: "run-pilot-001",
                  source_id: "demo-business-postgres"
                },
                source_id: "demo-business-postgres",
                state: "submitted"
              }
            })
        });
      }

      return new Promise(() => {});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      await HomePage({
        searchParams: {
          history_item_type: "run",
          history_record_id: "run-pilot-001",
          question: "Pilot source preview",
          source_id: "demo-business-postgres",
          state: "completed"
        }
      })
    );

    fireEvent.click(screen.getByRole("button", { name: /revise attempt/i }));
    expect(screen.getByText(/revised attempt draft/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/natural-language question/i), {
      target: { value: "Pilot source preview with revised filter" }
    });
    fireEvent.submit(screen.getByRole("button", { name: /submit for preview/i }).closest("form")!);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/requests/preview",
        expect.objectContaining({
          body: JSON.stringify({
            question: "Pilot source preview with revised filter",
            source_id: "demo-business-postgres",
            revise_from: {
              item_type: "run",
              request_id: "request-pilot-001",
              candidate_id: "candidate-pilot-001",
              run_id: "run-pilot-001"
            }
          }),
          method: "POST"
        })
      );
    });
  });

  it("submits a revised preview attempt from execution-denied run context", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();

      if (url.endsWith("/operator/workflow")) {
        const payload = pilotWorkflowPayload();
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              ...payload,
              history: [
                ...payload.history,
                {
                  auditEvents: [
                    {
                      candidateId: "candidate-pilot-001",
                      candidateState: "preview_ready",
                      eventId: "run-pilot-denied-001",
                      eventType: "execution_denied",
                      occurredAt: "2026-04-21T14:40:00Z",
                      primaryDenyCode: "DENY_EXECUTION_POLICY",
                      requestId: "request-pilot-001",
                      resultTruncated: null,
                      rowCount: null,
                      sourceId: "demo-business-postgres"
                    }
                  ],
                  executedEvidence: [],
                  itemType: "run",
                  label: "Pilot denied run",
                  lifecycleState: "execution_denied",
                  occurredAt: "2026-04-21T14:40:00Z",
                  recordId: "run-pilot-denied-001",
                  requestId: "request-pilot-001",
                  retrievedCitations: [],
                  runState: "execution_denied",
                  sourceId: "demo-business-postgres",
                  sourceLabel: "Demo business PostgreSQL / approved_vendor_spend"
                }
              ]
            })
        });
      }

      if (url.endsWith("/requests/preview")) {
        return new Promise(() => {});
      }

      return new Promise(() => {});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      await HomePage({
        searchParams: {
          history_item_type: "run",
          history_record_id: "run-pilot-denied-001",
          question: "Pilot denied run",
          source_id: "demo-business-postgres",
          state: "execution_denied"
        }
      })
    );

    fireEvent.click(screen.getByRole("button", { name: /revise attempt/i }));
    fireEvent.change(screen.getByLabelText(/natural-language question/i), {
      target: { value: "Pilot denied run with revised filter" }
    });
    fireEvent.submit(screen.getByRole("button", { name: /submit for preview/i }).closest("form")!);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/requests/preview",
        expect.objectContaining({
          body: JSON.stringify({
            question: "Pilot denied run with revised filter",
            source_id: "demo-business-postgres",
            revise_from: {
              item_type: "run",
              request_id: "request-pilot-001",
              candidate_id: "candidate-pilot-001",
              run_id: "run-pilot-denied-001"
            }
          }),
          method: "POST"
        })
      );
    });
  });

  it("submits a revised preview attempt from request-backed failure history", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();

      if (url.endsWith("/operator/workflow")) {
        const payload = pilotWorkflowPayload();
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              ...payload,
              history: [
                {
                  auditEvents: [],
                  executedEvidence: [],
                  itemType: "request",
                  label: "Pilot unavailable preview",
                  lifecycleState: "preview_unavailable",
                  occurredAt: "2026-04-21T14:42:00Z",
                  recordId: "request-pilot-unavailable-001",
                  retrievedCitations: [],
                  sourceId: "demo-business-postgres",
                  sourceLabel: "Demo business PostgreSQL / approved_vendor_spend"
                },
                ...payload.history
              ]
            })
        });
      }

      if (url.endsWith("/requests/preview")) {
        return new Promise(() => {});
      }

      return new Promise(() => {});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      await HomePage({
        searchParams: {
          history_item_type: "request",
          history_record_id: "request-pilot-unavailable-001",
          question: "Pilot unavailable preview",
          source_id: "demo-business-postgres",
          state: "review_denied"
        }
      })
    );

    fireEvent.click(screen.getByRole("button", { name: /revise attempt/i }));
    fireEvent.change(screen.getByLabelText(/natural-language question/i), {
      target: { value: "Pilot unavailable preview with revised source context" }
    });
    fireEvent.submit(screen.getByRole("button", { name: /submit for preview/i }).closest("form")!);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/requests/preview",
        expect.objectContaining({
          body: JSON.stringify({
            question: "Pilot unavailable preview with revised source context",
            source_id: "demo-business-postgres",
            revise_from: {
              item_type: "request",
              request_id: "request-pilot-unavailable-001"
            }
          }),
          method: "POST"
        })
      );
    });
  });
});
