FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend:/app \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

RUN useradd --create-home --uid 10001 app && chown app:app /app
COPY --chown=app:app backend/ ./backend/
COPY --chown=app:app ml/ ./ml/
COPY --chown=app:app data/processed/ ./data/processed/
COPY --chown=app:app data/docs/ ./data/docs/
COPY --chown=app:app docker/backend_entrypoint.py docker/rag_entrypoint.py docker/rag_bundle.py ./docker/
USER app
EXPOSE 8000
ENTRYPOINT ["python", "/app/docker/backend_entrypoint.py"]
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
