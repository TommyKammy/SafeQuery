from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings


@lru_cache
def get_engine(database_url: str) -> Engine:
    return create_engine(database_url)


def require_preview_submission_session() -> Iterator[Session]:
    settings = get_settings()
    with Session(get_engine(str(settings.app_postgres_url))) as session:
        yield session
