import { QueryWorkflowShell, resolveWorkflowState } from "../components/query-workflow-shell";
import { getAppConfig } from "../lib/config";
import { DEFAULT_HEALTH_SNAPSHOT } from "../lib/health";

type SearchParamValue = string | string[] | undefined;

type HomePageProps = {
  searchParams?: Promise<Record<string, SearchParamValue>> | Record<string, SearchParamValue>;
};

function readParam(value: SearchParamValue): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }

  return value;
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const params = searchParams ? await searchParams : {};
  const config = getAppConfig();
  const question = readParam(params.question)?.trim() || "List the top 10 approved vendors by quarterly spend.";
  const state = resolveWorkflowState(readParam(params.state));

  return (
    <QueryWorkflowShell
      apiUrl={config.publicApiBaseUrl}
      health={DEFAULT_HEALTH_SNAPSHOT}
      question={question}
      state={state}
    />
  );
}
