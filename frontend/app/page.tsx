import { QueryWorkflowShell } from "../components/query-workflow-shell";
import { getAppConfig } from "../lib/config";
import { DEFAULT_HEALTH_SNAPSHOT } from "../lib/health";
import {
  getOperatorWorkflowSnapshot,
  type OperatorWorkflowSnapshot,
  type SourceOption
} from "../lib/operator-workflow";

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

function hasEntitlementAffectingGovernanceDrift(source: SourceOption): boolean {
  return source.governanceBindings.some(
    (binding) => binding.affectsEntitlement && binding.state !== "valid"
  );
}

function resolveLocalDemoSourceId(
  operatorWorkflow: OperatorWorkflowSnapshot,
  requestedSourceId?: string,
  localDemoDefaultSourceId?: string
): string | undefined {
  if (requestedSourceId) {
    return requestedSourceId;
  }

  if (!localDemoDefaultSourceId || operatorWorkflow.status !== "live") {
    return undefined;
  }

  const source = operatorWorkflow.sources.find(
    (sourceOption) => sourceOption.sourceId === localDemoDefaultSourceId
  );
  if (
    !source ||
    source.activationPosture !== "active" ||
    hasEntitlementAffectingGovernanceDrift(source)
  ) {
    return undefined;
  }

  return source.sourceId;
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const params = searchParams ? await searchParams : {};
  const config = getAppConfig();
  const question = readParam(params.question)?.trim() || "List the top 10 approved vendors by quarterly spend.";
  const sourceId = readParam(params.source_id)?.trim();
  const historyRecordId = readParam(params.history_record_id)?.trim();
  const state = readParam(params.state)?.trim();
  const operatorWorkflow = await getOperatorWorkflowSnapshot(config.apiInternalBaseUrl);
  const resolvedSourceId = resolveLocalDemoSourceId(
    operatorWorkflow,
    sourceId,
    config.localDemoDefaultSourceId
  );

  return (
    <QueryWorkflowShell
      apiUrl={config.publicApiBaseUrl}
      health={DEFAULT_HEALTH_SNAPSHOT}
      operatorWorkflow={operatorWorkflow}
      question={question}
      historyRecordId={historyRecordId}
      sourceId={resolvedSourceId}
      state={state}
    />
  );
}
