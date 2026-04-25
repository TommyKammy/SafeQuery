from functools import lru_cache
from typing import Annotated, Literal, Optional

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    PostgresDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class BusinessPostgresSourceSettings(BaseModel):
    identity: Literal["business_postgres_source_generation"] = (
        "business_postgres_source_generation"
    )
    url: PostgresDsn


class BusinessMssqlSourceSettings(BaseModel):
    identity: Literal["business_mssql_source_execution"] = (
        "business_mssql_source_execution"
    )
    connection_string: str


SQLGenerationProvider = Literal["disabled", "local_llm", "vanna"]


class SQLGenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: SQLGenerationProvider = "disabled"
    local_llm_base_url: Optional[AnyHttpUrl] = None
    local_llm_model: Optional[str] = None
    vanna_base_url: Optional[AnyHttpUrl] = None
    vanna_model: Optional[str] = None
    vanna_api_key: Optional[SecretStr] = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    retry_count: int = Field(default=1, ge=0, le=3)
    circuit_breaker_failure_threshold: int = Field(default=3, ge=1, le=10)


class SourceRoleTelemetry(BaseModel):
    application_postgres_persistence: Literal["configured"] = "configured"
    business_postgres_source_generation: Literal["configured", "unconfigured"]
    business_mssql_source_execution: Literal["configured", "unconfigured"]


class SourcePostureTelemetry(BaseModel):
    source_posture: Literal["coherent"] = "coherent"
    configured_source_count: int
    source_roles: SourceRoleTelemetry


class Settings(BaseSettings):
    app_name: str = "SafeQuery API"
    environment: Literal["development", "test", "staging", "production"] = "development"
    app_postgres_url: PostgresDsn
    dev_auth_enabled: bool = False
    session_signing_key: Optional[SecretStr] = None
    business_postgres_source_url: Optional[PostgresDsn] = None
    business_mssql_source_connection_string: Optional[str] = None
    sql_generation_provider: SQLGenerationProvider = "disabled"
    sql_generation_local_llm_base_url: Optional[AnyHttpUrl] = None
    sql_generation_local_llm_model: Optional[str] = None
    sql_generation_vanna_base_url: Optional[AnyHttpUrl] = None
    sql_generation_vanna_model: Optional[str] = None
    sql_generation_vanna_api_key: Optional[SecretStr] = None
    sql_generation_timeout_seconds: int = Field(default=30, ge=1, le=300)
    sql_generation_retry_count: int = Field(default=1, ge=0, le=3)
    sql_generation_circuit_breaker_failure_threshold: int = Field(
        default=3,
        ge=1,
        le=10,
    )
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    model_config = SettingsConfigDict(
        env_prefix="SAFEQUERY_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]

        return value

    @field_validator(
        "sql_generation_local_llm_model",
        "sql_generation_vanna_model",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None

        return value

    @field_validator("sql_generation_vanna_api_key")
    @classmethod
    def _reject_placeholder_vanna_api_key(
        cls,
        value: Optional[SecretStr],
    ) -> Optional[SecretStr]:
        if value is None:
            return value

        normalized = value.get_secret_value().strip().lower()
        if normalized in {"change-me", "changeme", "todo", "placeholder", "example"}:
            raise ValueError(
                "SAFEQUERY_SQL_GENERATION_VANNA_API_KEY must come from a trusted "
                "credential source, not a placeholder value."
            )

        return value

    @model_validator(mode="after")
    def _validate_distinct_postgres_roles_and_generation_provider(self) -> "Settings":
        if self.dev_auth_enabled and self.environment not in {"development", "test"}:
            raise ValueError(
                "SAFEQUERY_DEV_AUTH_ENABLED is only allowed when "
                "SAFEQUERY_ENVIRONMENT is development or test."
            )

        source_url = self.business_postgres_source_url
        if source_url is not None and str(source_url) == str(self.app_postgres_url):
            raise ValueError(
                "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must not reuse "
                "SAFEQUERY_APP_POSTGRES_URL."
            )

        if (
            self.sql_generation_provider == "local_llm"
            and self.sql_generation_local_llm_base_url is None
        ):
            raise ValueError(
                "SAFEQUERY_SQL_GENERATION_LOCAL_LLM_BASE_URL must be configured "
                "when SAFEQUERY_SQL_GENERATION_PROVIDER=local_llm."
            )

        if (
            self.sql_generation_provider == "vanna"
            and self.sql_generation_vanna_base_url is None
        ):
            raise ValueError(
                "SAFEQUERY_SQL_GENERATION_VANNA_BASE_URL must be configured "
                "when SAFEQUERY_SQL_GENERATION_PROVIDER=vanna."
            )

        return self

    @property
    def app_postgres_identity(self) -> Literal["application_postgres_persistence"]:
        return "application_postgres_persistence"

    def require_business_postgres_source(self) -> BusinessPostgresSourceSettings:
        source_url = self.business_postgres_source_url
        if source_url is None:
            raise RuntimeError(
                "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must be configured before "
                "the business PostgreSQL generation source can be used."
            )

        return BusinessPostgresSourceSettings(url=source_url)

    def require_business_mssql_source(self) -> BusinessMssqlSourceSettings:
        connection_string = self.business_mssql_source_connection_string
        if connection_string is None:
            normalized_connection_string = ""
        else:
            normalized_connection_string = connection_string.strip()

        if not normalized_connection_string:
            raise RuntimeError(
                "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING must be "
                "configured before the business MSSQL execution source can be used."
            )

        return BusinessMssqlSourceSettings(
            connection_string=normalized_connection_string
        )

    @property
    def sql_generation(self) -> SQLGenerationSettings:
        return SQLGenerationSettings(
            provider=self.sql_generation_provider,
            local_llm_base_url=self.sql_generation_local_llm_base_url,
            local_llm_model=self.sql_generation_local_llm_model,
            vanna_base_url=self.sql_generation_vanna_base_url,
            vanna_model=self.sql_generation_vanna_model,
            vanna_api_key=self.sql_generation_vanna_api_key,
            timeout_seconds=self.sql_generation_timeout_seconds,
            retry_count=self.sql_generation_retry_count,
            circuit_breaker_failure_threshold=(
                self.sql_generation_circuit_breaker_failure_threshold
            ),
        )

    def source_posture_telemetry(self) -> SourcePostureTelemetry:
        business_postgres_role = (
            "configured"
            if self.business_postgres_source_url is not None
            else "unconfigured"
        )

        connection_string = self.business_mssql_source_connection_string
        if connection_string is None:
            business_mssql_role = "unconfigured"
        elif connection_string.strip():
            business_mssql_role = "configured"
        else:
            raise RuntimeError(
                "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING must not be "
                "whitespace-only when source posture smoke checks run."
            )

        source_roles = SourceRoleTelemetry(
            business_postgres_source_generation=business_postgres_role,
            business_mssql_source_execution=business_mssql_role,
        )

        return SourcePostureTelemetry(
            configured_source_count=sum(
                role == "configured"
                for role in source_roles.model_dump().values()
            ),
            source_roles=source_roles,
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return self.cors_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
