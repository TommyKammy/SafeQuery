export type HealthSnapshot = {
  detail: string;
  status: "ok" | "degraded" | "unreachable";
};

type HealthPayload = {
  database?: { status?: string };
  status?: string;
};

export const DEFAULT_HEALTH_SNAPSHOT: HealthSnapshot = {
  detail: "Backend health is loading in the background so the workflow shell stays available.",
  status: "degraded"
};

export function getDegradedHealthSnapshot(statusCode: number): HealthSnapshot {
  return {
    detail: `Backend health endpoint returned HTTP ${statusCode}.`,
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
