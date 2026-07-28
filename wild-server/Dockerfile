ARG UV_BASE_IMAGE=ghcr.io/astral-sh/uv:latest
ARG PYTHON_BASE_IMAGE=python:3.12-slim

FROM ${UV_BASE_IMAGE} AS uv
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

COPY --from=uv /uv /usr/local/bin/uv

ENV PATH="/app/.venv/bin:${PATH}" \
    UV_LINK_MODE=copy

# Install dependencies first so Docker can reuse the layer when only app code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
