from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services.health import check_database_health

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="Minimum SafeQuery control-plane baseline.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
def read_root() -> dict[str, object]:
    return {
        "service": "safequery-api",
        "status": "baseline",
        "health": "/health",
        "seams": {
            "auth": "reserved",
            "guard": "reserved",
            "execution": "reserved",
            "audit": "reserved",
        },
    }


@app.get("/health")
def read_health() -> JSONResponse:
    database = check_database_health(settings.database_url)
    healthy = database["status"] == "ok"

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "service": "safequery-api",
            "database": database,
        },
    )
