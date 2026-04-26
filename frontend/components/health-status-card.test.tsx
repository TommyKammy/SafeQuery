import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HealthStatusCard } from "./health-status-card";

describe("HealthStatusCard", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows a neutral loading state before the probe completes", () => {
    render(<HealthStatusCard apiUrl="http://127.0.0.1:8000" />);

    expect(screen.getByText("loading")).toBeInTheDocument();
    expect(
      screen.getByText(/backend health is loading in the background so the workflow shell stays available/i)
    ).toBeInTheDocument();
  });

  it("treats malformed json responses as degraded instead of unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => {
          throw new SyntaxError("Unexpected token < in JSON");
        }
      }))
    );

    render(<HealthStatusCard apiUrl="http://127.0.0.1:8000" />);

    await waitFor(() => {
      expect(screen.getByText("degraded")).toBeInTheDocument();
    });

    expect(screen.getByText(/invalid payload/i)).toBeInTheDocument();
  });

  it("keeps transport failures in the unreachable state", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fetch failed"))));

    render(<HealthStatusCard apiUrl="http://127.0.0.1:8000" />);

    await waitFor(() => {
      expect(screen.getByText("unreachable")).toBeInTheDocument();
    });

    expect(screen.getByText(/not reachable from the frontend yet/i)).toBeInTheDocument();
  });

  it("summarizes the bounded operator aggregate without rendering raw details", async () => {
    const secretDetail = "postgresql://safequery:secret@db/safequery";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          database: { status: "ok" },
          operator_health: {
            components: {
              active_source_connectivity: { status: "degraded", raw: secretDetail },
              audit_persistence: { status: "ok" },
              generation_adapter: { status: "disabled" },
              source_registry: { status: "ok" }
            },
            status: "degraded"
          },
          status: "degraded"
        })
      }))
    );

    render(<HealthStatusCard apiUrl="http://127.0.0.1:8000" />);

    await waitFor(() => {
      expect(screen.getByText("degraded")).toBeInTheDocument();
    });

    expect(screen.getByText(/source registry ok/i)).toBeInTheDocument();
    expect(screen.getByText(/active source connectivity degraded/i)).toBeInTheDocument();
    expect(screen.getByText(/generation adapter disabled/i)).toBeInTheDocument();
    expect(screen.getByText(/audit persistence ok/i)).toBeInTheDocument();
    expect(screen.queryByText(secretDetail)).not.toBeInTheDocument();
  });
});
