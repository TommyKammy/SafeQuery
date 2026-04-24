import { QueryWorkflowShell, resolveWorkflowState } from "../components/query-workflow-shell";
import { getAppConfig } from "../lib/config";
import { DEFAULT_HEALTH_SNAPSHOT } from "../lib/health";
import { getOperatorWorkflowSnapshot } from "../lib/operator-workflow";

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
  const sourceId = readParam(params.source_id)?.trim();
  const state = resolveWorkflowState(readParam(params.state));
  const operatorWorkflow = await getOperatorWorkflowSnapshot(config.apiInternalBaseUrl);

  return (
    <QueryWorkflowShell
      apiUrl={config.publicApiBaseUrl}
      health={DEFAULT_HEALTH_SNAPSHOT}
      operatorWorkflow={operatorWorkflow}
      question={question}
      sourceId={sourceId}
      state={state}
    />
  );
}
