ARG PYTHON_BASE_IMAGE=python:3.12-slim

FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

ARG UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV UV_INDEX_URL=${UV_INDEX_URL} \
    PIP_INDEX_URL=${UV_INDEX_URL} \
    PATH="/app/.venv/bin:${PATH}" \
    UV_LINK_MODE=copy

# 通过 pip 安装 uv（走 PyPI 镜像，避免从 ghcr.io 慢速拉取）
RUN pip install --no-cache-dir uv

# Install dependencies first so Docker can reuse the layer when only app code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
