export type AppConfig = {
  apiInternalBaseUrl: string;
  publicApiBaseUrl: string;
};

function getRequiredUrl(name: string): string {
  const value = process.env[name];

  if (!value || value.trim().length === 0) {
    throw new Error(`Missing required environment variable: ${name}`);
  }

  return new URL(value).toString().replace(/\/$/, "");
}

export function getAppConfig(): AppConfig {
  return {
    apiInternalBaseUrl: getRequiredUrl("API_INTERNAL_BASE_URL"),
    publicApiBaseUrl: getRequiredUrl("NEXT_PUBLIC_API_BASE_URL")
  };
}
