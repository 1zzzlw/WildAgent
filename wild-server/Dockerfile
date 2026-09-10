ARG PYTHON_BASE_IMAGE=python:3.12-slim

FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

ARG UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG UV_VERSION=0.11.14
ENV UV_INDEX_URL=${UV_INDEX_URL} \
    PIP_INDEX_URL=${UV_INDEX_URL} \
    PATH="/app/.venv/bin:${PATH}" \
    UV_LINK_MODE=copy

# 固定 uv 版本，避免构建工具自动升级后与已提交的 uv.lock 产生兼容差异。
RUN pip install --no-cache-dir "uv==${UV_VERSION}"

# Install dependencies first so Docker can reuse the layer when only app code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project --index-url ${UV_INDEX_URL}

COPY . .

# 生产通过单文件 bind mount 把宿主机 .env 映射到此目录；目录必须在镜像中存在。
RUN mkdir -p /app/runtime-config

# 按 config.yaml 的 required_documents 清单检查镜像内容，避免固定篇数与知识库
# 正常重构冲突，也阻止缺少任一正式文档的镜像进入部署。
RUN python -c "from pathlib import Path; from scripts.deploy.deployment_preflight import validate_knowledge_documents; files, required = validate_knowledge_documents(Path('storage/knowledge_base')); print(f'knowledge_base_files={len(files)} required_documents={len(required)}')"

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=8 \
    CMD python -c "import urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3); raise SystemExit(0 if response.status == 200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
