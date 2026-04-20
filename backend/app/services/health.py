from collections.abc import Mapping

import psycopg


def check_database_health(database_url: str) -> Mapping[str, str]:
    try:
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except Exception as exc:  # pragma: no cover - exercised through stack smoke verification.
        return {
            "status": "error",
            "detail": exc.__class__.__name__,
        }

    return {
        "status": "ok",
        "detail": "ready",
    }
