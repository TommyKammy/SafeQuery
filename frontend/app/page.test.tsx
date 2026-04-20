import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HomePage from "./page";

describe("HomePage", () => {
  beforeEach(() => {
    process.env.API_INTERNAL_BASE_URL = "http://127.0.0.1:8000";
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        json: async () => ({
          database: {
            status: "ok"
          },
          status: "ok"
        }),
        ok: true
      }))
    );
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
    expect(screen.getByRole("link", { name: /error state/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /empty state/i })).toBeInTheDocument();
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

  it("renders explicit empty and error placeholder states", async () => {
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

    expect(screen.getByText(/error state reached/i)).toBeInTheDocument();
    expect(screen.getByText(/blocked pending trusted prerequisite/i)).toBeInTheDocument();
  });
});
