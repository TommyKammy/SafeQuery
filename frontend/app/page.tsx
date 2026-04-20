import { QueryWorkflowShell, resolveWorkflowState } from "../components/query-workflow-shell";
import { getAppConfig } from "../lib/config";

type HealthSnapshot = {
  detail: string;
  status: "ok" | "degraded" | "unreachable";
};

type SearchParamValue = string | string[] | undefined;

type HomePageProps = {
  searchParams?: Promise<Record<string, SearchParamValue>> | Record<string, SearchParamValue>;
};

async function getHealthSnapshot(internalApiUrl: string): Promise<HealthSnapshot> {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;

  try {
    const controller = new AbortController();
    timeoutId = setTimeout(() => controller.abort(), 3000);

    const response = await fetch(`${internalApiUrl}/health`, {
      cache: "no-store",
      signal: controller.signal
    });

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
  } finally {
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId);
    }
  }
}

function readParam(value: SearchParamValue): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }

  return value;
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const params = searchParams ? await searchParams : {};
  const config = getAppConfig();
  const health = await getHealthSnapshot(config.apiInternalBaseUrl);
  const question = readParam(params.question)?.trim() || "List the top 10 approved vendors by quarterly spend.";
  const state = resolveWorkflowState(readParam(params.state));

  return (
    <QueryWorkflowShell
      apiUrl={config.publicApiBaseUrl}
      health={health}
      question={question}
      state={state}
    />
  );
}
