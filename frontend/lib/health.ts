export type HealthSnapshot = {
  detail: string;
  status: "ok" | "loading" | "degraded" | "unreachable";
};

export type HealthPayload = {
  database?: { status?: string };
  operator_health?: {
    components?: Record<string, { status?: string }>;
    status?: string;
  };
  status?: string;
};

export const DEFAULT_HEALTH_SNAPSHOT: HealthSnapshot = {
  detail: "Backend health is loading in the background so the workflow shell stays available.",
  status: "loading"
};

export function getDegradedHealthSnapshot(statusCode: number): HealthSnapshot {
  return {
    detail: `Backend health endpoint returned HTTP ${statusCode}.`,
    status: "degraded"
  };
}

export function getMalformedHealthSnapshot(): HealthSnapshot {
  return {
    detail: "Backend health endpoint returned an invalid payload.",
    status: "degraded"
  };
}

export function getHealthSnapshotFromPayload(payload: HealthPayload): HealthSnapshot {
  const operatorHealth = payload.operator_health;
  if (operatorHealth && typeof operatorHealth.status !== "string") {
    return getMalformedHealthSnapshot();
  }

  const components = operatorHealth?.components;
  if (components && (typeof components !== "object" || Array.isArray(components))) {
    return getMalformedHealthSnapshot();
  }

  const componentSummary = components
    ? [
        ["source registry", components.source_registry?.status],
        ["active source connectivity", components.active_source_connectivity?.status],
        ["generation adapter", components.generation_adapter?.status],
        ["audit persistence", components.audit_persistence?.status]
      ]
        .map(([label, status]) => `${label} ${typeof status === "string" ? status : "unknown"}`)
        .join("; ")
    : "operator aggregate unavailable";

  return {
    detail: `Backend is ${payload.status ?? "unknown"}, PostgreSQL is ${payload.database?.status ?? "unknown"}, and ${componentSummary}.`,
    status: payload.status === "ok" ? "ok" : "degraded"
  };
}

export function getUnreachableHealthSnapshot(): HealthSnapshot {
  return {
    detail: "Backend health check is not reachable from the frontend yet.",
    status: "unreachable"
  };
}

export function isHealthPayload(value: unknown): value is HealthPayload {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
