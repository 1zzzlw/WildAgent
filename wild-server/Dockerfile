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

# 防止 .dockerignore 或构建上下文误排除生产 RAG 知识库。当前正式知识库不少于
# 30 个 Markdown；缺失时在镜像构建阶段失败，不能部署一个会清空 Chroma 的镜像。
RUN python -c "from pathlib import Path; root=Path('storage/knowledge_base'); files=list(root.rglob('*.md')); assert (root / 'BLUEPRINT-SPEC-MINIMAL.md').is_file(), 'minimal blueprint spec missing from image'; assert len(files) >= 30, f'incomplete knowledge base: {len(files)} markdown files'; print(f'knowledge_base_files={len(files)}')"

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=8 \
    CMD python -c "import urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3); raise SystemExit(0 if response.status == 200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
