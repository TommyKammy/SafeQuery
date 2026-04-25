from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.services.demo_source_seed import seed_demo_source_governance


def main() -> None:
    settings = get_settings()
    with Session(get_engine(str(settings.app_postgres_url))) as session:
        result = seed_demo_source_governance(session)

    print(
        json.dumps(
            {
                "source_id": result.source_id,
                "created": result.created,
                "source_record_id": str(result.source_record_id),
                "dataset_contract_id": str(result.dataset_contract_id),
                "schema_snapshot_id": str(result.schema_snapshot_id),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
