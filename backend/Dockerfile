FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/pyproject.toml ./pyproject.toml
COPY backend/README.md ./README.md
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

EXPOSE 8000

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
