import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HomePage from "./page";
import { resolveWorkflowState } from "../components/query-workflow-shell";

function workflowPayload(sourceLabel = "SAP spend cube / approved_vendor_spend") {
  return {
    history: [
      {
        itemType: "request",
        label: "Approved vendor spend",
        lifecycleState: "previewed",
        occurredAt: "2026-04-21T14:18:00Z",
        recordId: "request-123",
        sourceId: "sap-approved-spend",
        sourceLabel
      }
    ],
    sources: [
      {
        activationPosture: "active",
        description: "Approved finance spend cube for governed preview and single-source execution.",
        displayLabel: sourceLabel,
        sourceId: "sap-approved-spend"
      },
      {
        activationPosture: "paused",
        description: "Historical archive is visible for posture review but not executable for preview.",
        displayLabel: "Legacy finance archive",
        sourceId: "legacy-finance-archive"
      }
    ]
  };
}

function stubWorkflowFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = input.toString();

    if (url.endsWith("/operator/workflow")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(workflowPayload())
      });
    }

    return new Promise(() => {});
  });
}

describe("HomePage", () => {
  beforeEach(() => {
    process.env.API_INTERNAL_BASE_URL = "http://127.0.0.1:8000";
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";

    vi.stubGlobal("fetch", stubWorkflowFetch());
  });

  afterEach(() => {
    cleanup();
    document.head.querySelectorAll('meta[name="safequery-csrf-token"]').forEach((node) => {
      node.remove();
    });
    vi.unstubAllGlobals();
  });

  it("shows the custom workflow states and review surfaces", async () => {
    render(await HomePage({}));

    expect(screen.getByRole("heading", { name: /query workflow/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit for preview/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /source/i })).toBeInTheDocument();
    expect(screen.getByText("Generated SQL")).toBeInTheDocument();
    expect(screen.getByText("Guard status")).toBeInTheDocument();
    expect(screen.getByText("Results")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review denied/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /empty state/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /compose the operator request/i })).toBeInTheDocument();
    expect(screen.getByText(/operator shell for governed question review, sql preview, and execution posture/i)).toBeInTheDocument();
    expect(screen.queryByText(/compose the analyst question/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/awaiting analyst review/i)).not.toBeInTheDocument();
  });

  it("renders source options from the live operator workflow payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                history: [],
                sources: [
                  {
                    activationPosture: "active",
                    description: "Live source returned by the backend contract.",
                    displayLabel: "ERP approved spend / live contract",
                    sourceId: "erp-approved-spend"
                  }
                ]
              })
          });
        }

        return new Promise(() => {});
      })
    );

    render(await HomePage({}));

    expect(
      screen.getByRole("option", { name: "ERP approved spend / live contract" })
    ).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /SAP spend cube/i })).not.toBeInTheDocument();
  });

  it("renders source-aware history rows from the live operator workflow payload", async () => {
    render(await HomePage({}));

    expect(screen.getByLabelText(/operator history/i)).toHaveTextContent("Approved vendor spend");
    expect(screen.getByLabelText(/operator history/i)).toHaveTextContent(
      "SAP spend cube / approved_vendor_spend"
    );
    expect(screen.getByLabelText(/operator history/i)).toHaveTextContent("previewed");
  });

  it("reopens history rows into anchored non-draft workflow states", async () => {
    render(await HomePage({}));

    const historyLink = within(screen.getByLabelText(/operator history/i)).getByRole("link", {
      name: /approved vendor spend/i
    });

    expect(historyLink).toHaveAttribute("href", expect.stringContaining("state=preview"));
    expect(historyLink).toHaveAttribute("href", expect.stringContaining("source_id=sap-approved-spend"));
    expect(historyLink).toHaveAttribute("href", expect.stringContaining("history_item_type=request"));
    expect(historyLink).toHaveAttribute("href", expect.stringContaining("history_record_id=request-123"));
    expect(historyLink).not.toHaveAttribute("href", expect.stringContaining("state=query"));
  });

  it("reopens denied candidates and terminal runs into their lifecycle states", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                history: [
                  {
                    guardStatus: "blocked",
                    itemType: "candidate",
                    label: "Blocked candidate",
                    lifecycleState: "blocked",
                    occurredAt: "2026-04-21T14:24:00Z",
                    recordId: "candidate-123",
                    sourceId: "sap-approved-spend",
                    sourceLabel: "SAP spend cube / approved_vendor_spend"
                  },
                  {
                    itemType: "run",
                    label: "Failed run",
                    lifecycleState: "failed",
                    occurredAt: "2026-04-21T14:35:00Z",
                    recordId: "run-123",
                    runState: "failed",
                    sourceId: "sap-approved-spend",
                    sourceLabel: "SAP spend cube / approved_vendor_spend"
                  }
                ],
                sources: workflowPayload().sources
              })
          });
        }

        return new Promise(() => {});
      })
    );

    render(await HomePage({}));

    const history = screen.getByLabelText(/operator history/i);
    const deniedCandidateLink = within(history).getByRole("link", { name: /blocked candidate/i });
    const failedRunLink = within(history).getByRole("link", { name: /failed run/i });

    expect(deniedCandidateLink).toHaveAttribute("href", expect.stringContaining("state=review_denied"));
    expect(deniedCandidateLink).toHaveAttribute(
      "href",
      expect.stringContaining("history_record_id=candidate-123")
    );
    expect(failedRunLink).toHaveAttribute("href", expect.stringContaining("state=failed"));
    expect(failedRunLink).toHaveAttribute("href", expect.stringContaining("history_record_id=run-123"));
  });

  it("reports malformed workflow payloads separately from unavailable transport", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.reject(new SyntaxError("Unexpected token < in JSON"))
          });
        }

        return new Promise(() => {});
      })
    );

    render(await HomePage({}));

    expect(screen.getByLabelText(/operator history/i)).toHaveTextContent("malformed");
    expect(
      screen.getByText(/backend workflow payload was malformed, so the source selector remains blocked/i)
    ).toBeInTheDocument();
  });

  it("renders normalized auth and entitlement workflow failures without leaking sensitive details", async () => {
    const secretDetail = "idp-token-should-not-render";
    const failureCases = [
      {
        code: "unauthenticated",
        message: "Sign in before submitting preview requests.",
        statusCopy: /sign in before loading the operator workflow/i
      },
      {
        code: "session_invalid",
        message: "Sign in again before submitting preview requests.",
        statusCopy: /operator session is no longer valid/i
      },
      {
        code: "csrf_failed",
        message: "Refresh the page before submitting preview requests.",
        statusCopy: /request freshness check failed/i
      },
      {
        code: "entitlement_denied",
        message: "The signed-in operator is not entitled to use that source.",
        statusCopy: /this source or workflow context/i
      }
    ] as const;

    for (const failureCase of failureCases) {
      cleanup();
      vi.stubGlobal(
        "fetch",
        vi.fn((input: RequestInfo | URL) => {
          const url = input.toString();

          if (url.endsWith("/operator/workflow")) {
            return Promise.resolve({
              ok: false,
              json: () =>
                Promise.resolve({
                  error: {
                    code: failureCase.code,
                    message: failureCase.message,
                    raw: secretDetail
                  }
                })
            });
          }

          return new Promise(() => {});
        })
      );

      render(await HomePage({}));

      expect(screen.getByLabelText(/operator history/i)).toHaveTextContent(failureCase.code);
      expect(screen.getByText(failureCase.statusCopy)).toBeInTheDocument();
      expect(screen.getByText(failureCase.message)).toBeInTheDocument();
      expect(screen.queryByText(secretDetail)).not.toBeInTheDocument();
    }
  });

  it("renders the shell before the health probe completes", async () => {
    const fetchMock = stubWorkflowFetch();
    vi.stubGlobal("fetch", fetchMock);

    render(await HomePage({}));

    expect(screen.getByRole("heading", { name: /query workflow/i })).toBeInTheDocument();
    expect(
      screen.getByText(/backend health is loading in the background so the workflow shell stays available/i)
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8000/health", expect.any(Object));
    });
  });

  it("navigates the submitted question into the preview state", async () => {
    render(
      await HomePage({
        searchParams: {
          question: "Show approved vendors by quarterly spend",
          source_id: "sap-approved-spend",
          state: "preview",
        }
      })
    );

    expect(screen.getByRole("heading", { name: /sql preview state/i })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Show approved vendors by quarterly spend")).toBeInTheDocument();
    expect(screen.getByText(/authoritative sql preview/i)).toBeInTheDocument();
    expect(screen.getByText(/no authoritative candidate selected/i)).toBeInTheDocument();
    expect(screen.queryByText(/placeholder sql generated from the question review surface/i)).not.toBeInTheDocument();
  });

  it("anchors reopened candidate previews to the URL history record", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                history: [
                  {
                    candidateSql: "select 'wrong candidate' as preview;",
                    guardStatus: "blocked",
                    itemType: "candidate",
                    label: "Earlier blocked candidate",
                    lifecycleState: "blocked",
                    occurredAt: "2026-04-21T14:20:00Z",
                    recordId: "candidate-wrong",
                    requestId: "request-wrong",
                    sourceId: "sap-approved-spend",
                    sourceLabel: "SAP spend cube / approved_vendor_spend"
                  },
                  {
                    candidateSql: "select vendor_name from approved_vendor_spend;",
                    guardStatus: "passed",
                    itemType: "candidate",
                    label: "Selected candidate",
                    lifecycleState: "preview_ready",
                    occurredAt: "2026-04-21T14:24:00Z",
                    recordId: "candidate-selected",
                    requestId: "request-selected",
                    sourceId: "sap-approved-spend",
                    sourceLabel: "SAP spend cube / approved_vendor_spend"
                  }
                ],
                sources: workflowPayload().sources
              })
          });
        }

        return new Promise(() => {});
      })
    );

    render(
      await HomePage({
        searchParams: {
          history_item_type: "candidate",
          history_record_id: "candidate-selected",
          question: "Selected candidate",
          source_id: "sap-approved-spend",
          state: "preview"
        }
      })
    );

    expect(screen.getByText("select vendor_name from approved_vendor_spend;")).toBeInTheDocument();
    expect(screen.getByText("request-selected")).toBeInTheDocument();
    expect(screen.getByText("candidate-selected")).toBeInTheDocument();
    expect(screen.queryByText("select 'wrong candidate' as preview;")).not.toBeInTheDocument();
    for (const completedLink of screen.getAllByRole("link", { name: /open completed state/i })) {
      expect(completedLink).toHaveAttribute(
        "href",
        expect.stringContaining("history_item_type=candidate")
      );
      expect(completedLink).toHaveAttribute(
        "href",
        expect.stringContaining("history_record_id=candidate-selected")
      );
    }
    expect(screen.getByRole("link", { name: /open empty state/i })).toHaveAttribute(
      "href",
      expect.stringContaining("history_record_id=candidate-selected")
    );
  });

  it("keeps reopened history source separate from a mismatched draft source", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                history: [
                  {
                    candidateSql: "select vendor_name from approved_vendor_spend;",
                    guardStatus: "passed",
                    itemType: "candidate",
                    label: "Selected SAP candidate",
                    lifecycleState: "preview_ready",
                    occurredAt: "2026-04-21T14:24:00Z",
                    recordId: "candidate-sap-selected",
                    requestId: "request-sap-selected",
                    sourceId: "sap-approved-spend",
                    sourceLabel: "SAP spend cube / approved_vendor_spend"
                  }
                ],
                sources: [
                  {
                    activationPosture: "active",
                    description: "Draft marketing source returned by the backend contract.",
                    displayLabel: "Marketing campaigns / campaign_spend",
                    sourceId: "marketing-campaign-spend"
                  },
                  {
                    activationPosture: "active",
                    description: "Candidate source returned by the backend contract.",
                    displayLabel: "SAP spend cube / approved_vendor_spend",
                    sourceId: "sap-approved-spend"
                  }
                ]
              })
          });
        }

        return new Promise(() => {});
      })
    );

    render(
      await HomePage({
        searchParams: {
          history_item_type: "candidate",
          history_record_id: "candidate-sap-selected",
          question: "Draft marketing question",
          source_id: "marketing-campaign-spend",
          state: "preview"
        }
      })
    );

    expect(screen.getByText("select vendor_name from approved_vendor_spend;")).toBeInTheDocument();
    expect(screen.getAllByText("SAP spend cube / approved_vendor_spend").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Marketing campaigns / campaign_spend").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/selected draft source does not match the reopened candidate source/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open completed state/i })).not.toBeInTheDocument();
  });

  it("submits the selected source and question to the preview API", async () => {
    const csrfToken = document.createElement("meta");
    csrfToken.name = "safequery-csrf-token";
    csrfToken.content = "csrf-from-session-bootstrap";
    document.head.appendChild(csrfToken);

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = input.toString();

      if (url.endsWith("/operator/workflow")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(workflowPayload())
        });
      }

      if (url.endsWith("/requests/preview")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              audit: {
                events: [],
                source_id: "sap-approved-spend",
                state: "recorded"
              },
              candidate: {
                candidate_id: "candidate-accepted-123",
                candidate_sql: null,
                dataset_contract_version: 1,
                guard_status: "pending",
                schema_snapshot_version: 1,
                source_family: "postgresql",
                source_flavor: "warehouse",
                source_id: "sap-approved-spend",
                state: "preview_ready"
              },
              evaluation: {
                source_id: "sap-approved-spend",
                state: "pending"
              },
              request: {
                question: "Show approved vendors by quarterly spend",
                request_id: "request-accepted-123",
                source_id: "sap-approved-spend",
                state: "submitted"
              }
            })
        });
      }

      return new Promise(() => {});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(await HomePage({}));

    fireEvent.change(screen.getByRole("combobox", { name: /source/i }), {
      target: { value: "sap-approved-spend" }
    });
    fireEvent.change(screen.getByLabelText(/natural-language question/i), {
      target: { value: "Show approved vendors by quarterly spend" }
    });
    fireEvent.submit(screen.getByRole("button", { name: /submit for preview/i }).closest("form")!);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/requests/preview",
        expect.objectContaining({
          body: JSON.stringify({
            question: "Show approved vendors by quarterly spend",
            source_id: "sap-approved-spend"
          }),
          credentials: "same-origin",
          headers: expect.objectContaining({
            "content-type": "application/json",
            "x-safequery-csrf": "csrf-from-session-bootstrap"
          }),
          method: "POST"
        })
      );
    });
    expect(screen.getByText(/preview request accepted/i)).toBeInTheDocument();
    expect(screen.getByText("candidate-accepted-123")).toBeInTheDocument();
    expect(screen.getByText(/canonical sql has not been generated for this candidate/i)).toBeInTheDocument();
    expect(screen.queryByText(/placeholder sql generated from the question review surface/i)).not.toBeInTheDocument();
  });

  it("maps authoritative preview API states without presenting them as successful SQL previews", async () => {
    const stateCases = [
      {
        candidateState: "pending_generation",
        expectedCopy: /preview generation pending/i,
        requestState: "submitted"
      },
      {
        candidateState: "denied",
        expectedCopy: /preview denied/i,
        requestState: "blocked"
      }
    ] as const;

    for (const stateCase of stateCases) {
      cleanup();
      const fetchMock = vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(workflowPayload())
          });
        }

        if (url.endsWith("/requests/preview")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                audit: {
                  events: [],
                  source_id: "sap-approved-spend",
                  state: "recorded"
                },
                candidate: {
                  candidate_id: `candidate-${stateCase.candidateState}`,
                  candidate_sql: null,
                  dataset_contract_version: 1,
                  guard_status: stateCase.candidateState === "denied" ? "blocked" : "pending",
                  schema_snapshot_version: 1,
                  source_family: "postgresql",
                  source_flavor: "warehouse",
                  source_id: "sap-approved-spend",
                  state: stateCase.candidateState
                },
                evaluation: {
                  source_id: "sap-approved-spend",
                  state: "pending"
                },
                request: {
                  question: "Show approved vendors by quarterly spend",
                  request_id: `request-${stateCase.requestState}`,
                  source_id: "sap-approved-spend",
                  state: stateCase.requestState
                }
              })
          });
        }

        return new Promise(() => {});
      });
      vi.stubGlobal("fetch", fetchMock);

      render(await HomePage({}));

      fireEvent.change(screen.getByRole("combobox", { name: /source/i }), {
        target: { value: "sap-approved-spend" }
      });
      fireEvent.change(screen.getByLabelText(/natural-language question/i), {
        target: { value: "Show approved vendors by quarterly spend" }
      });
      fireEvent.submit(screen.getByRole("button", { name: /submit for preview/i }).closest("form")!);

      expect(await screen.findByText(stateCase.expectedCopy)).toBeInTheDocument();
      expect(screen.queryByText(/preview request accepted/i)).not.toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: /sql preview state/i })).not.toBeInTheDocument();
    }
  });

  it("executes only preview-ready candidates and maps denied or canceled execute responses to recovery states", async () => {
    const csrfToken = document.createElement("meta");
    csrfToken.name = "safequery-csrf-token";
    csrfToken.content = "csrf-from-session-bootstrap";
    document.head.appendChild(csrfToken);

    const executeResponses = [
      {
        body: {
          error: {
            code: "execution_denied",
            message: "Candidate execution was denied.",
            raw: "driver-secret-should-not-render"
          }
        },
        expectedHeading: /execution denied state/i,
        expectedStatus: /execute denied/i,
        status: 403
      },
      {
        body: {
          audit: {
            events: [
              {
                candidate_state: "canceled",
                event_type: "execution_failed",
                query_candidate_id: "candidate-selected"
              }
            ]
          },
          error: {
            code: "execution_unavailable",
            message: "Candidate execution is unavailable."
          }
        },
        expectedHeading: /canceled state/i,
        expectedStatus: /execution canceled/i,
        status: 503
      }
    ] as const;

    for (const executeResponse of executeResponses) {
      cleanup();
      document.head.appendChild(csrfToken);
      const fetchMock = vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                history: [
                  {
                    candidateSql: "select vendor_name from approved_vendor_spend;",
                    guardStatus: "passed",
                    itemType: "candidate",
                    label: "Selected candidate",
                    lifecycleState: "preview_ready",
                    occurredAt: "2026-04-21T14:24:00Z",
                    recordId: "candidate-selected",
                    requestId: "request-selected",
                    sourceId: "sap-approved-spend",
                    sourceLabel: "SAP spend cube / approved_vendor_spend"
                  }
                ],
                sources: workflowPayload().sources
              })
          });
        }

        if (url.endsWith("/candidates/candidate-selected/execute")) {
          return Promise.resolve({
            ok: false,
            status: executeResponse.status,
            json: () => Promise.resolve(executeResponse.body)
          });
        }

        return new Promise(() => {});
      });
      vi.stubGlobal("fetch", fetchMock);

      render(
        await HomePage({
          searchParams: {
            history_item_type: "candidate",
            history_record_id: "candidate-selected",
            question: "Selected candidate",
            source_id: "sap-approved-spend",
            state: "preview"
          }
        })
      );

      fireEvent.click(screen.getByRole("button", { name: /execute reviewed candidate/i }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "http://127.0.0.1:8000/candidates/candidate-selected/execute",
          expect.objectContaining({
            body: JSON.stringify({
              selected_source_id: "sap-approved-spend"
            }),
            credentials: "same-origin",
            headers: expect.objectContaining({
              "content-type": "application/json",
              "x-safequery-csrf": "csrf-from-session-bootstrap"
            }),
            method: "POST"
          })
        );
      });

      await waitFor(() => {
        expect(screen.getAllByText(executeResponse.expectedStatus).length).toBeGreaterThan(0);
      });
      expect(
        screen.getByRole("heading", { name: executeResponse.expectedHeading })
      ).toBeInTheDocument();
      expect(screen.queryByText(/execution completed/i)).not.toBeInTheDocument();
      expect(screen.queryByText("driver-secret-should-not-render")).not.toBeInTheDocument();
    }
  });

  it("keeps execute disabled for non-authorized candidate states", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                history: [
                  {
                    candidateSql: null,
                    guardStatus: "pending",
                    itemType: "candidate",
                    label: "Pending candidate",
                    lifecycleState: "pending_generation",
                    occurredAt: "2026-04-21T14:24:00Z",
                    recordId: "candidate-pending",
                    requestId: "request-pending",
                    sourceId: "sap-approved-spend",
                    sourceLabel: "SAP spend cube / approved_vendor_spend"
                  }
                ],
                sources: workflowPayload().sources
              })
          });
        }

        return new Promise(() => {});
      })
    );

    render(
      await HomePage({
        searchParams: {
          history_item_type: "candidate",
          history_record_id: "candidate-pending",
          question: "Pending candidate",
          source_id: "sap-approved-spend",
          state: "preview"
        }
      })
    );

    expect(screen.getByRole("button", { name: /execute reviewed candidate/i })).toBeDisabled();
    expect(screen.getByText(/no executable candidate/i)).toBeInTheDocument();
  });

  it("maps malformed and unavailable preview submission failures distinctly", async () => {
    const failureCases = [
      {
        expectedCopy: /malformed_preview_response/i,
        response: {
          ok: true,
          json: () =>
            Promise.resolve({
              candidate: {
                source_id: "wrong-source",
                state: "preview_ready"
              },
              request: {
                source_id: "sap-approved-spend",
                state: "submitted"
              }
            })
        }
      },
      {
        expectedCopy: /preview_submission_unavailable/i,
        response: {
          ok: false,
          status: 503,
          json: () => Promise.reject(new SyntaxError("Unexpected token < in JSON"))
        }
      },
      {
        expectedCopy: /preview_source_unavailable/i,
        response: {
          ok: false,
          status: 422,
          json: () =>
            Promise.resolve({
              error: {
                code: "preview_source_unavailable",
                message: "Selected source is unavailable for preview."
              }
            })
        }
      },
      {
        expectedCopy: /preview_source_malformed/i,
        response: {
          ok: false,
          status: 422,
          json: () =>
            Promise.resolve({
              error: {
                code: "preview_source_malformed",
                message: "Selected source governance is malformed."
              }
            })
        }
      }
    ] as const;

    for (const failureCase of failureCases) {
      cleanup();
      const fetchMock = vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(workflowPayload())
          });
        }

        if (url.endsWith("/requests/preview")) {
          return Promise.resolve(failureCase.response);
        }

        return new Promise(() => {});
      });
      vi.stubGlobal("fetch", fetchMock);

      render(await HomePage({}));

      fireEvent.change(screen.getByRole("combobox", { name: /source/i }), {
        target: { value: "sap-approved-spend" }
      });
      fireEvent.change(screen.getByLabelText(/natural-language question/i), {
        target: { value: "Show approved vendors by quarterly spend" }
      });
      fireEvent.submit(screen.getByRole("button", { name: /submit for preview/i }).closest("form")!);

      expect(await screen.findByRole("alert")).toHaveTextContent(failureCase.expectedCopy);
      expect(screen.queryByText(/preview request accepted/i)).not.toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: /sql preview state/i })).not.toBeInTheDocument();
    }
  });

  it("renders preview API auth and entitlement failure envelopes without leaking details", async () => {
    const failureCases = [
      {
        code: "csrf_failed",
        message: "Refresh the page before submitting preview requests."
      },
      {
        code: "entitlement_denied",
        message: "The signed-in operator is not entitled to use that source."
      }
    ] as const;
    const secretDetail = "session-cookie-should-not-render";

    for (const failureCase of failureCases) {
      cleanup();
      const fetchMock = vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(workflowPayload())
          });
        }

        if (url.endsWith("/requests/preview")) {
          return Promise.resolve({
            ok: false,
            json: () =>
              Promise.resolve({
                error: {
                  code: failureCase.code,
                  message: failureCase.message,
                  raw: secretDetail
                }
              })
          });
        }

        return new Promise(() => {});
      });
      vi.stubGlobal("fetch", fetchMock);

      render(await HomePage({}));

      fireEvent.change(screen.getByRole("combobox", { name: /source/i }), {
        target: { value: "sap-approved-spend" }
      });
      fireEvent.submit(screen.getByRole("button", { name: /submit for preview/i }).closest("form")!);

      expect(await screen.findByRole("alert")).toHaveTextContent(failureCase.code);
      expect(screen.getByRole("alert")).toHaveTextContent(failureCase.message);
      expect(screen.queryByText(secretDetail)).not.toBeInTheDocument();
    }
  });

  it("requires an explicit source selection before preview state can be entered", async () => {
    render(
      await HomePage({
        searchParams: {
          question: "Show approved vendors by quarterly spend",
          state: "preview"
        }
      })
    );

    expect(screen.getByRole("heading", { name: /query input state/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /source/i })).toHaveValue("");
    expect(
      screen.getByText(/select an executable source before preview can be requested/i)
    ).toBeInTheDocument();
  });

  it("keeps source selection read-only after a preview-bound source is chosen", async () => {
    render(
      await HomePage({
        searchParams: {
          question: "Show approved vendors by quarterly spend",
          source_id: "sap-approved-spend",
          state: "preview"
        }
      })
    );

    expect(screen.queryByRole("combobox", { name: /source/i })).not.toBeInTheDocument();
    expect(screen.getAllByText(/sap spend cube \/ approved_vendor_spend/i)).not.toHaveLength(0);
  });

  it("does not render placeholder result rows or fabricated run context in product workflow views", async () => {
    render(
      await HomePage({
        searchParams: {
          question: "Show approved vendors by quarterly spend",
          source_id: "sap-approved-spend",
          state: "completed"
        }
      })
    );

    expect(screen.getByRole("heading", { name: /completed state/i })).toBeInTheDocument();
    expect(screen.queryByText(/northwind health/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/harbor transit/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/blue summit labs/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/placeholder rows only/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/placeholder query results/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/run-sq-204/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/2026-04-21 14:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/placeholder only/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/authentication placeholder/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/results placeholder/i)).not.toBeInTheDocument();
  });

  it("renders selected terminal run context from authoritative history", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                history: [
                  {
                    itemType: "run",
                    label: "Selected completed run",
                    lifecycleState: "completed",
                    occurredAt: "2026-04-21T14:42:17+09:00",
                    recordId: "run-authoritative-282",
                    runState: null,
                    sourceId: "sap-approved-spend",
                    sourceLabel: "Authoritative run source / approved_vendor_spend"
                  }
                ],
                sources: [
                  {
                    activationPosture: "active",
                    description: "Registry fallback source label should not override selected run context.",
                    displayLabel: "Registry fallback source label",
                    sourceId: "sap-approved-spend"
                  }
                ]
              })
          });
        }

        return new Promise(() => {});
      })
    );

    render(
      await HomePage({
        searchParams: {
          history_item_type: "run",
          history_record_id: "run-authoritative-282",
          question: "Selected completed run",
          source_id: "sap-approved-spend",
          state: "completed"
        }
      })
    );

    const lifecycleSection = screen
      .getByRole("heading", { name: /source and lifecycle context/i })
      .closest("section");
    expect(lifecycleSection).not.toBeNull();
    const lifecycleContext = within(lifecycleSection!);

    expect(lifecycleContext.getByText("Authoritative run source / approved_vendor_spend")).toBeInTheDocument();
    expect(lifecycleContext.getByText("run-authoritative-282")).toBeInTheDocument();
    expect(lifecycleContext.getByText("2026-04-21T14:42:17+09:00")).toBeInTheDocument();
    expect(lifecycleContext.queryByText("2026-04-21 05:42 UTC")).not.toBeInTheDocument();
    expect(lifecycleContext.getByText("completed")).toBeInTheDocument();
    expect(lifecycleContext.queryByText("Registry fallback source label")).not.toBeInTheDocument();
    expect(screen.queryByText(/placeholder rows only/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/placeholder query results/i)).not.toBeInTheDocument();
  });

  it("renders completed result metadata only from the selected authoritative run", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                history: [
                  {
                    itemType: "run",
                    label: "Selected completed run",
                    lifecycleState: "completed",
                    occurredAt: "2026-04-21T14:42:17+09:00",
                    recordId: "run-authoritative-282",
                    resultTruncated: true,
                    rowCount: 12,
                    runState: "completed",
                    sourceId: "sap-approved-spend",
                    sourceLabel: "Authoritative run source / approved_vendor_spend"
                  },
                  {
                    itemType: "run",
                    label: "Sibling completed run",
                    lifecycleState: "completed",
                    occurredAt: "2026-04-21T14:43:17+09:00",
                    recordId: "run-sibling-283",
                    resultTruncated: false,
                    rowCount: 99,
                    runState: "completed",
                    sourceId: "sap-approved-spend",
                    sourceLabel: "Authoritative run source / approved_vendor_spend"
                  }
                ],
                sources: workflowPayload().sources
              })
          });
        }

        return new Promise(() => {});
      })
    );

    render(
      await HomePage({
        searchParams: {
          history_item_type: "run",
          history_record_id: "run-authoritative-282",
          question: "Selected completed run",
          source_id: "sap-approved-spend",
          state: "completed"
        }
      })
    );

    const resultsSection = screen.getByRole("heading", { name: /completed result set/i }).closest("section");
    expect(resultsSection).not.toBeNull();
    const results = within(resultsSection!);

    expect(results.getByText(/authoritative result metadata/i)).toBeInTheDocument();
    expect(results.getByText(/12 rows/i)).toBeInTheDocument();
    expect(results.getByText(/truncated/i)).toBeInTheDocument();
    expect(results.queryByText(/99 rows/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/placeholder query results/i)).not.toBeInTheDocument();
  });

  it("renders audit context, executed evidence, and retrieved citations without sensitive fields", async () => {
    const unsafeLocalPath = "/" + ["Users", "example", "secret-should-not-render"].join("/");

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString();

        if (url.endsWith("/operator/workflow")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                history: [
                  {
                    auditEvents: [
                      {
                        eventId: "00000000-0000-4000-8000-000000000012",
                        eventType: "execution_completed",
                        occurredAt: "2026-04-21T14:42:17+09:00",
                        requestId: "request-selected",
                        candidateId: "candidate-selected",
                        sourceId: "sap-approved-spend",
                        rowCount: 12,
                        resultTruncated: false,
                        sessionId: "session-secret-should-not-render"
                      }
                    ],
                    executedEvidence: [
                      {
                        authority: "backend_execution_result",
                        canAuthorizeExecution: false,
                        candidateId: "candidate-selected",
                        executionAuditEventId: "00000000-0000-4000-8000-000000000012",
                        executionAuditEventType: "execution_completed",
                        rowCount: 12,
                        resultTruncated: false,
                        sourceId: "sap-approved-spend",
                        sourceFamily: "postgresql",
                        sourceFlavor: "warehouse",
                        connectionString: "postgres://secret-should-not-render"
                      }
                    ],
                    itemType: "run",
                    label: "Selected completed run",
                    lifecycleState: "completed",
                    occurredAt: "2026-04-21T14:42:17+09:00",
                    recordId: "run-authoritative-287",
                    retrievedCitations: [
                      {
                        assetId: "spend-metric-definition",
                        assetKind: "metric_definition",
                        authority: "advisory_context",
                        canAuthorizeExecution: false,
                        citationLabel: "Approved spend metric definition",
                        sourceId: "sap-approved-spend",
                        sourceFamily: "postgresql",
                        sourceFlavor: "warehouse",
                        localPath: unsafeLocalPath
                      }
                    ],
                    resultTruncated: false,
                    rowCount: 12,
                    runState: "completed",
                    sourceId: "sap-approved-spend",
                    sourceLabel: "SAP spend cube / approved_vendor_spend"
                  }
                ],
                sources: workflowPayload().sources
              })
          });
        }

        return new Promise(() => {});
      })
    );

    render(
      await HomePage({
        searchParams: {
          history_item_type: "run",
          history_record_id: "run-authoritative-287",
          question: "Selected completed run",
          source_id: "sap-approved-spend",
          state: "completed"
        }
      })
    );

    expect(screen.getByRole("heading", { name: /operator evidence context/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/audit lifecycle events/i)).toHaveTextContent("execution_completed");
    expect(screen.getByLabelText(/audit lifecycle events/i)).toHaveTextContent(
      "00000000-0000-4000-8000-000000000012"
    );
    expect(screen.getByLabelText(/executed evidence/i)).toHaveTextContent(
      "backend_execution_result"
    );
    expect(screen.getByLabelText(/executed evidence/i)).toHaveTextContent("12 rows");
    expect(screen.getByLabelText(/retrieved citation context/i)).toHaveTextContent(
      "Approved spend metric definition"
    );
    expect(screen.getByLabelText(/retrieved citation context/i)).toHaveTextContent(
      "advisory_context"
    );
    expect(screen.getAllByText(/cannot authorize execution: false/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/session-secret-should-not-render/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret-should-not-render/i)).not.toBeInTheDocument();
    expect(screen.queryByText(unsafeLocalPath)).not.toBeInTheDocument();
  });

  it("renders explicit empty and review-denied unavailable states", async () => {
    const { rerender } = render(
      await HomePage({
        searchParams: {
          question: "Show approved vendors by quarterly spend",
          source_id: "sap-approved-spend",
          state: "empty"
        }
      })
    );

    expect(screen.getByText(/empty state reached/i)).toBeInTheDocument();

    rerender(
      await HomePage({
        searchParams: {
          question: "Show approved vendors by quarterly spend",
          source_id: "sap-approved-spend",
          state: "error"
        }
      })
    );

    expect(screen.getByText(/review denied state reached/i)).toBeInTheDocument();
    expect(screen.getByText(/review denied before execution/i)).toBeInTheDocument();
  });

  it("maps terminal outcomes to distinct operator-facing states with anchored context", async () => {
    const question = "Show approved vendors by quarterly spend";
    const terminalStateExpectations = [
      {
        state: "review_denied",
        heading: /review denied state/i,
        status: /review denied before execution/i,
        lifecycle: /lifecycle state/i,
        identity: /^Draft only$/i
      },
      {
        state: "completed",
        heading: /completed state/i,
        status: /execution completed/i,
        lifecycle: /lifecycle posture/i,
        identity: /No submitted record yet/i
      },
      {
        state: "failed",
        heading: /failed state/i,
        status: /execution failed after run start/i,
        lifecycle: /lifecycle posture/i,
        identity: /No submitted record yet/i
      },
      {
        state: "canceled",
        heading: /canceled state/i,
        status: /execution canceled before completion/i,
        lifecycle: /lifecycle posture/i,
        identity: /No submitted record yet/i
      },
      {
        state: "execution_denied",
        heading: /execution denied state/i,
        status: /execution denied at execute time/i,
        lifecycle: /lifecycle posture/i,
        identity: /No submitted record yet/i
      }
    ] as const;

    for (const terminalState of terminalStateExpectations) {
      cleanup();
      render(
        await HomePage({
          searchParams: {
          question,
          source_id: "sap-approved-spend",
          state: terminalState.state
        }
      })
      );

      expect(screen.getByRole("heading", { name: terminalState.heading })).toBeInTheDocument();
      expect(screen.getAllByText(terminalState.status).length).toBeGreaterThan(0);
      expect(screen.getByText(/source identity/i)).toBeInTheDocument();
      expect(screen.getByText(/request (identity|posture)/i)).toBeInTheDocument();
      expect(screen.getByText(terminalState.lifecycle)).toBeInTheDocument();
      expect(screen.getAllByText(terminalState.identity).length).toBeGreaterThan(0);
    }
  });

  it("keeps pre-submission states in a draft-only posture until a real request exists", async () => {
    const { rerender } = render(await HomePage({}));

    expect(screen.getByText(/request posture/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^Draft only$/i)).not.toHaveLength(0);
    expect(screen.getByText(/lifecycle posture/i)).toBeInTheDocument();
    expect(screen.getByText(/no submitted record yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/req-sq-204/i)).not.toBeInTheDocument();

    rerender(
      await HomePage({
        searchParams: {
          state: "signin"
        }
      })
    );

    expect(screen.getByRole("heading", { name: /sign in state/i })).toBeInTheDocument();
    expect(screen.getByText(/request posture/i)).toBeInTheDocument();
    expect(screen.queryByText(/req-sq-204/i)).not.toBeInTheDocument();
  });

  it("falls back to the query state for inherited object keys", () => {
    expect(resolveWorkflowState("toString")).toBe("query");
  });
});
