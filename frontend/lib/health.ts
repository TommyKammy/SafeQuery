export type HealthSnapshot = {
  detail: string;
  status: "ok" | "loading" | "degraded" | "unreachable";
};

export type HealthPayload = {
  database?: { status?: string };
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
  return {
    detail: `Backend is ${payload.status ?? "unknown"} and PostgreSQL is ${payload.database?.status ?? "unknown"}.`,
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
