"use client";

import { useEffect, useState } from "react";
import {
  DEFAULT_HEALTH_SNAPSHOT,
  getDegradedHealthSnapshot,
  getHealthSnapshotFromPayload,
  getMalformedHealthSnapshot,
  getUnreachableHealthSnapshot,
  isHealthPayload,
  type HealthSnapshot
} from "../lib/health";

type HealthStatusCardProps = {
  apiUrl: string;
  initialHealth?: HealthSnapshot;
};

export function HealthStatusCard({
  apiUrl,
  initialHealth = DEFAULT_HEALTH_SNAPSHOT
}: HealthStatusCardProps) {
  const [health, setHealth] = useState(initialHealth);

  useEffect(() => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 3000);
    let cancelled = false;

    async function probeHealth() {
      try {
        const response = await fetch(`${apiUrl}/health`, {
          cache: "no-store",
          signal: controller.signal
        });

        if (cancelled) {
          return;
        }

        if (!response.ok) {
          setHealth(getDegradedHealthSnapshot(response.status));
          return;
        }

        const payload = (await response.json()) as unknown;

        if (!isHealthPayload(payload)) {
          setHealth(getMalformedHealthSnapshot());
          return;
        }

        if (!cancelled) {
          setHealth(getHealthSnapshotFromPayload(payload));
        }
      } catch (error) {
        if (!cancelled) {
          if (error instanceof DOMException && error.name === "AbortError") {
            setHealth(getUnreachableHealthSnapshot());
            return;
          }

          if (error instanceof TypeError) {
            setHealth(getUnreachableHealthSnapshot());
            return;
          }

          setHealth(getMalformedHealthSnapshot());
        }
      } finally {
        window.clearTimeout(timeoutId);
      }
    }

    void probeHealth();

    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [apiUrl]);

  return (
    <div className="meta-card">
      <span className="meta-label">Stack status</span>
      <strong className={`status-text status-${health.status}`}>{health.status}</strong>
      <span className="meta-copy">{health.detail}</span>
    </div>
  );
}
