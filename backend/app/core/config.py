from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SafeQuery API"
    environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: PostgresDsn
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
    def cors_origins_list(self) -> list[str]:
        return self.cors_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
