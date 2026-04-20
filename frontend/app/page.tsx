import { HealthCard } from "../components/health-card";

type HealthSnapshot = {
  detail: string;
  status: "ok" | "degraded" | "unreachable";
};

const publicApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const internalApiUrl = process.env.API_INTERNAL_BASE_URL ?? publicApiUrl;

async function getHealthSnapshot(): Promise<HealthSnapshot> {
  try {
    const response = await fetch(`${internalApiUrl}/health`, { cache: "no-store" });

    if (!response.ok) {
      return {
        detail: `Backend health endpoint returned HTTP ${response.status}.`,
        status: "degraded"
      };
    }

    const payload = (await response.json()) as {
      database?: { status?: string };
      status?: string;
    };

    return {
      detail: `Backend is ${payload.status ?? "unknown"} and PostgreSQL is ${payload.database?.status ?? "unknown"}.`,
      status: payload.status === "ok" ? "ok" : "degraded"
    };
  } catch {
    return {
      detail: "Backend health check is not reachable from the frontend yet.",
      status: "unreachable"
    };
  }
}

const seams = [
  {
    name: "Auth boundary",
    description: "Reserved for session establishment, CSRF, and role-aware route protection."
  },
  {
    name: "Guard boundary",
    description: "Reserved for SQL validation, deny rules, and approval gating."
  },
  {
    name: "Execution boundary",
    description: "Reserved for approved query dispatch, result limits, and kill-switch behavior."
  },
  {
    name: "Audit boundary",
    description: "Reserved for lifecycle events, approvals, denials, and runtime traces."
  }
];

export default async function HomePage() {
  const health = await getHealthSnapshot();

  return (
    <main className="shell">
      <section className="hero panel">
        <p className="eyebrow">SafeQuery</p>
        <h1>Minimum application baseline</h1>
        <p className="lede">
          This checkpoint establishes the local repository shape for the Next.js UI, FastAPI
          control plane, and PostgreSQL system of record. The implementation is intentionally
          limited to placeholder surfaces and stack health.
        </p>
      </section>

      <HealthCard apiUrl={publicApiUrl} detail={health.detail} status={health.status} />

      <section className="panel">
        <div className="section-heading">
          <p className="eyebrow">Planned seams</p>
          <p className="section-copy">
            These boundaries stay explicit so later work can add capability without moving the
            trusted backend edge.
          </p>
        </div>
        <div className="seam-grid">
          {seams.map((seam) => (
            <article className="seam-card" key={seam.name}>
              <h2>{seam.name}</h2>
              <p>{seam.description}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
