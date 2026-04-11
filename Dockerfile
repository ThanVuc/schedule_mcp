# ---- builder ----
FROM python:3.12-slim AS builder

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# system deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# install poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# install dependencies (better caching)
COPY pyproject.toml poetry.lock* ./
RUN poetry lock --no-interaction && poetry install --no-root --only main

# 🔥 copy source code AFTER deps (important for caching)
COPY . .

# ---- runtime ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# copy only runtime artifacts from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/main.py /app/main.py
COPY --from=builder /app/application /app/application
COPY --from=builder /app/boostrap /app/boostrap
COPY --from=builder /app/constant /app/constant
COPY --from=builder /app/domain /app/domain
COPY --from=builder /app/infrastructure /app/infrastructure
COPY --from=builder /app/interface /app/interface

# optional: create non-root user (recommended)
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# run app
CMD ["/app/.venv/bin/python", "main.py"]
