FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies (libpq for asyncpg)
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies first (for layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy source code
COPY src/ ./src/
COPY config/ ./config/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Run the app
CMD ["uvicorn", "content_autopilot.app:app", "--host", "0.0.0.0", "--port", "8000"]
