import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HomePage from "./page";
import { resolveWorkflowState } from "../components/query-workflow-shell";

describe("HomePage", () => {
  beforeEach(() => {
    process.env.API_INTERNAL_BASE_URL = "http://127.0.0.1:8000";
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";

    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the custom workflow states and review surfaces", async () => {
    render(await HomePage({}));

    expect(screen.getByRole("heading", { name: /query workflow/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate preview/i })).toBeInTheDocument();
    expect(screen.getByText("Generated SQL")).toBeInTheDocument();
    expect(screen.getByText("Guard status")).toBeInTheDocument();
    expect(screen.getByText("Results")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review denied/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /empty state/i })).toBeInTheDocument();
  });

  it("renders the shell before the health probe completes", async () => {
    const fetchMock = vi.fn(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    render(await HomePage({}));

    expect(screen.getByRole("heading", { name: /query workflow/i })).toBeInTheDocument();
    expect(
      screen.getByText(/backend health is loading in the background so the workflow shell stays available/i)
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  it("navigates the submitted question into the preview state", async () => {
    render(
      await HomePage({
        searchParams: {
          question: "Show approved vendors by quarterly spend",
          state: "preview"
        }
      })
    );

    expect(screen.getByRole("heading", { name: /sql preview state/i })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Show approved vendors by quarterly spend")).toBeInTheDocument();
    expect(screen.getAllByText(/sql preview placeholder/i)).not.toHaveLength(0);
  });

  it("renders explicit empty and review-denied placeholder states", async () => {
    const { rerender } = render(
      await HomePage({
        searchParams: {
          question: "Show approved vendors by quarterly spend",
          state: "empty"
        }
      })
    );

    expect(screen.getByText(/empty state reached/i)).toBeInTheDocument();

    rerender(
      await HomePage({
        searchParams: {
          question: "Show approved vendors by quarterly spend",
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
        lifecycle: /candidate state/i,
        identity: /candidate-sq-204/i
      },
      {
        state: "completed",
        heading: /completed state/i,
        status: /execution completed with rows/i,
        lifecycle: /run state/i,
        identity: /run-sq-204/i
      },
      {
        state: "failed",
        heading: /failed state/i,
        status: /execution failed after run start/i,
        lifecycle: /run state/i,
        identity: /run-sq-204/i
      },
      {
        state: "canceled",
        heading: /canceled state/i,
        status: /execution canceled before completion/i,
        lifecycle: /run state/i,
        identity: /run-sq-204/i
      },
      {
        state: "execution_denied",
        heading: /execution denied state/i,
        status: /execution denied at execute time/i,
        lifecycle: /run state/i,
        identity: /run-sq-204/i
      }
    ] as const;

    for (const terminalState of terminalStateExpectations) {
      cleanup();
      render(
        await HomePage({
          searchParams: {
            question,
            state: terminalState.state
          }
        })
      );

      expect(screen.getByRole("heading", { name: terminalState.heading })).toBeInTheDocument();
      expect(screen.getByText(terminalState.status)).toBeInTheDocument();
      expect(screen.getByText(/source identity/i)).toBeInTheDocument();
      expect(screen.getByText(/request identity/i)).toBeInTheDocument();
      expect(screen.getByText(terminalState.lifecycle)).toBeInTheDocument();
      expect(screen.getByText(terminalState.identity)).toBeInTheDocument();
    }
  });

  it("falls back to the query state for inherited object keys", () => {
    expect(resolveWorkflowState("toString")).toBe("query");
  });
});
