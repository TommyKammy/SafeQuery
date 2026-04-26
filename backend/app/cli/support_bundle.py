from __future__ import annotations

import json
import sys

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.services.health import check_database_health, check_sql_generation_runtime_health
from app.services.support_bundle import build_support_bundle


def main() -> None:
    settings = get_settings()
    database = check_database_health(str(settings.app_postgres_url))
    sql_generation = check_sql_generation_runtime_health(settings.sql_generation)
    with Session(get_engine(str(settings.app_postgres_url))) as session:
        bundle = build_support_bundle(
            session,
            settings=settings,
            database=database,
            sql_generation=sql_generation,
        )

    print(json.dumps(bundle.model_dump(mode="json", by_alias=True), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
