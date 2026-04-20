from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SafeQuery API"
    environment: str = "development"
    database_url: str = "postgresql://safequery:safequery@postgres:5432/safequery"
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_prefix="SAFEQUERY_",
        case_sensitive=False,
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
