export type AppConfig = {
  apiInternalBaseUrl: string;
  localDemoDefaultSourceId?: string;
  publicApiBaseUrl: string;
};

const LOCAL_DEMO_SOURCE_ID = "demo-business-postgres";

function getRequiredUrl(name: string): string {
  const value = process.env[name];

  if (!value || value.trim().length === 0) {
    throw new Error(`Missing required environment variable: ${name}`);
  }

  return new URL(value).toString().replace(/\/$/, "");
}

function getLocalDemoDefaultSourceId(): string | undefined {
  const environment = process.env.SAFEQUERY_ENVIRONMENT?.trim().toLowerCase();
  if (environment !== "development" && environment !== "test") {
    return undefined;
  }

  const configuredSourceId = process.env.SAFEQUERY_LOCAL_DEMO_SOURCE_ID?.trim();
  return configuredSourceId || LOCAL_DEMO_SOURCE_ID;
}

export function getAppConfig(): AppConfig {
  return {
    apiInternalBaseUrl: getRequiredUrl("API_INTERNAL_BASE_URL"),
    localDemoDefaultSourceId: getLocalDemoDefaultSourceId(),
    publicApiBaseUrl: getRequiredUrl("NEXT_PUBLIC_API_BASE_URL")
  };
}
