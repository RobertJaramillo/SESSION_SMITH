# Backend API image (FastAPI + Uvicorn). Build context is the repo root so the
# image can include synthetic-data/ for the demo seeder.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ /app/backend/
COPY synthetic-data/ /app/synthetic-data/

EXPOSE 8000

# Overridden by compose to run migrations + seed before serving.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
