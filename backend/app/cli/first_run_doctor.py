from __future__ import annotations

import json
import sys

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.services.first_run_doctor import run_first_run_doctor


def main() -> None:
    settings = get_settings()
    with Session(get_engine(str(settings.app_postgres_url))) as session:
        result = run_first_run_doctor(session)

    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    if result.status == "fail":
        raise SystemExit(1)
    if result.status == "degraded":
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
