from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PostgresDsn, field_validator
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


class Settings(BaseSettings):
    app_name: str = "SafeQuery API"
    environment: Literal["development", "test", "staging", "production"] = "development"
    app_postgres_url: PostgresDsn
    business_postgres_source_url: PostgresDsn | None = None
    business_mssql_source_connection_string: str | None = None
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

        if str(source_url) == str(self.app_postgres_url):
            raise RuntimeError(
                "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must not reuse "
                "SAFEQUERY_APP_POSTGRES_URL."
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
    def cors_origins_list(self) -> list[str]:
        return self.cors_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
