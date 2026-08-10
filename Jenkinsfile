pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  parameters {
    string(name: 'SSH_CREDENTIALS_ID', defaultValue: 'wild-agent-prod-ssh', description: 'Jenkins UI 中配置的 SSH 私钥凭据 ID')
    booleanParam(name: 'DEPLOY_ENABLED', defaultValue: true, description: 'main/master 分支构建成功后是否部署到服务器')
    booleanParam(name: 'REMOTE_VALIDATE_ENABLED', defaultValue: true, description: '是否在远程服务器用 Docker 执行前后端验证')
    string(name: 'DEPLOY_SSH_USER', defaultValue: 'root', description: '部署服务器 SSH 用户')
    string(name: 'DEPLOY_SSH_HOST', defaultValue: '39.106.183.13', description: '部署服务器地址')
    string(name: 'DEPLOY_SSH_PORT', defaultValue: '22', description: '部署服务器 SSH 端口')
    string(name: 'REMOTE_WORK_DIR', defaultValue: '/opt/wild-agent/builds', description: '远程服务器临时构建目录')
    string(name: 'DEPLOY_DATA_DIR', defaultValue: '/opt/wild-agent/storage', description: '远程服务器运行时数据目录')
    string(name: 'DEPLOY_ENV_FILE', defaultValue: '/opt/wild-agent/.env', description: '远程服务器后端容器 env 文件；不存在时部署失败并保留旧容器')
    string(name: 'PRESENCE_GEOIP_DB', defaultValue: '/app/storage/geoip/GeoLite2-City.mmdb', description: '后端容器内 GeoLite2 City 数据库路径')
  }

  environment {
    PROJECT = 'wild-agent'
    NPM_REGISTRY = 'https://registry.npmmirror.com'
    UV_INDEX_URL = 'https://mirrors.aliyun.com/pypi/simple/'
    UV_VERSION = '0.11.14'
    PYTHON_BASE_IMAGE = 'python:3.12-slim'
    NODE_BASE_IMAGE = 'node:22-alpine'
    NGINX_BASE_IMAGE = 'nginx:alpine'
    PATH = "D:\\software\\Git\\usr\\bin;${env.PATH}"

    DEPLOY_SSH_USER = "${params.DEPLOY_SSH_USER}"
    DEPLOY_SSH_HOST = "${params.DEPLOY_SSH_HOST}"
    DEPLOY_SSH_PORT = "${params.DEPLOY_SSH_PORT}"
    REMOTE_WORK_DIR = "${params.REMOTE_WORK_DIR}"
    DEPLOY_DATA_DIR = "${params.DEPLOY_DATA_DIR}"
    DEPLOY_ENV_FILE = "${params.DEPLOY_ENV_FILE}"
    PRESENCE_GEOIP_DB = "${params.PRESENCE_GEOIP_DB}"
  }

  stages {
    stage('初始化') {
      steps {
        script {
          env.COMMIT_SHA = sh(returnStdout: true, script: 'git rev-parse HEAD').trim()
          env.COMMIT_SHORT = sh(returnStdout: true, script: 'git rev-parse --short=12 HEAD').trim()
          def detectedBranch = env.BRANCH_NAME ?: env.GIT_BRANCH ?: sh(returnStdout: true, script: 'git rev-parse --abbrev-ref HEAD').trim()
          env.BUILD_BRANCH = detectedBranch.replaceFirst(/^origin\//, '').replaceFirst(/^\*\//, '')
          env.REF_SLUG = env.BUILD_BRANCH.replaceAll(/[^A-Za-z0-9_.-]+/, '-').toLowerCase()
          env.IS_PULL_REQUEST = (env.CHANGE_ID ? true : false).toString()
          env.IS_RELEASE_BRANCH = (!env.CHANGE_ID && (env.BUILD_BRANCH == 'main' || env.BUILD_BRANCH == 'master')).toString()

          def safeJobName = (env.JOB_NAME ?: env.PROJECT).replaceAll(/[^A-Za-z0-9_.-]+/, '-').toLowerCase()
          env.REMOTE_RELEASE_DIR = "${env.REMOTE_WORK_DIR}/${safeJobName}-${env.BUILD_NUMBER}-${env.COMMIT_SHORT}"
          env.IMAGE_SERVER_NAME = "${env.PROJECT}/wild-server:${env.REF_SLUG}-${env.COMMIT_SHORT}"
          env.IMAGE_WEB_NAME = "${env.PROJECT}/wild-web:${env.REF_SLUG}-${env.COMMIT_SHORT}"
          env.IMAGE_SERVER_LATEST = "${env.PROJECT}/wild-server:latest"
          env.IMAGE_WEB_LATEST = "${env.PROJECT}/wild-web:latest"

          echo "branch=${env.BUILD_BRANCH}, pull_request=${env.IS_PULL_REQUEST}, release=${env.IS_RELEASE_BRANCH}, commit=${env.COMMIT_SHORT}"
          echo "remote release dir=${env.REMOTE_RELEASE_DIR}"
          echo "server image=${env.IMAGE_SERVER_NAME}"
          echo "web image=${env.IMAGE_WEB_NAME}"
        }
      }
    }

    stage('上传源码到远程服务器') {
      when {
        expression { return env.IS_PULL_REQUEST != 'true' }
      }
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: params.SSH_CREDENTIALS_ID, keyFileVariable: 'SSH_KEY')]) {
          sh '''
            set -eu
            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

            echo "=== 测试 SSH 连接 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" "hostname && docker --version"

            echo "=== 准备远程构建目录 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" "
              set -eu
              mkdir -p '$REMOTE_WORK_DIR'
              case '$REMOTE_RELEASE_DIR' in
                '$REMOTE_WORK_DIR'/*) rm -rf '$REMOTE_RELEASE_DIR' ;;
                *) echo '非法远程构建目录: $REMOTE_RELEASE_DIR'; exit 1 ;;
              esac
              mkdir -p '$REMOTE_RELEASE_DIR'
            "

            echo "=== 上传当前 Git 提交源码 ==="
            git archive --format=tar HEAD | ssh $SSH_OPTS "$DEPLOY_TARGET" "tar -xf - -C '$REMOTE_RELEASE_DIR'"
          '''
        }
      }
    }

    stage('远程前端编译检查') {
      when {
        allOf {
          expression { return env.IS_PULL_REQUEST != 'true' }
          expression { return params.REMOTE_VALIDATE_ENABLED }
        }
      }
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: params.SSH_CREDENTIALS_ID, keyFileVariable: 'SSH_KEY')]) {
          sh '''
            set -eu
            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

            ssh $SSH_OPTS "$DEPLOY_TARGET" \
              "REMOTE_RELEASE_DIR='$REMOTE_RELEASE_DIR' NODE_BASE_IMAGE='$NODE_BASE_IMAGE' NPM_REGISTRY='$NPM_REGISTRY' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu
cd "$REMOTE_RELEASE_DIR/wild-web"
docker run --rm \
  -e NPM_REGISTRY="$NPM_REGISTRY" \
  -v "$PWD:/app" \
  -w /app \
  "$NODE_BASE_IMAGE" \
  sh -lc 'npm config set registry "$NPM_REGISTRY" && npm ci && npm run build'
REMOTE_SCRIPT
          '''
        }
      }
    }

    stage('远程后端语法检查') {
      when {
        allOf {
          expression { return env.IS_PULL_REQUEST != 'true' }
          expression { return params.REMOTE_VALIDATE_ENABLED }
        }
      }
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: params.SSH_CREDENTIALS_ID, keyFileVariable: 'SSH_KEY')]) {
          sh '''
            set -eu
            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

            ssh $SSH_OPTS "$DEPLOY_TARGET" \
              "REMOTE_RELEASE_DIR='$REMOTE_RELEASE_DIR' PYTHON_BASE_IMAGE='$PYTHON_BASE_IMAGE' UV_INDEX_URL='$UV_INDEX_URL' UV_VERSION='$UV_VERSION' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu
cd "$REMOTE_RELEASE_DIR/wild-server"
docker run --rm \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e UV_INDEX_URL="$UV_INDEX_URL" \
  -e UV_VERSION="$UV_VERSION" \
  -e CHAT__NAME=ci-dummy-chat \
  -e CHAT__API_KEY=ci-placeholder \
  -e CHAT__BASE_URL=http://127.0.0.1:9/v1 \
  -e RAG__ALLOW_HASH_FALLBACK=true \
  -e RAG__PERSIST_DIR=/tmp/wild-agent-ci-chroma \
  -v "$PWD:/app" \
  -w /app \
  "$PYTHON_BASE_IMAGE" \
  sh -lc '
    set -eu
    pip install --no-cache-dir "uv==$UV_VERSION" -i "$UV_INDEX_URL" --trusted-host mirrors.aliyun.com
    python -m compileall app/
    python -m py_compile main.py
    # 上传目录是本次构建的临时副本；在 Linux 上补齐平台锁信息，后续 Docker
    # 构建继续使用同一份临时 uv.lock，不修改 Git 仓库中的工作区。
    uv lock
    uv run --frozen --with pytest python -m pytest tests -q
  '
REMOTE_SCRIPT
          '''
        }
      }
    }

    stage('远程构建 Docker 镜像') {
      when {
        expression { return env.IS_RELEASE_BRANCH == 'true' }
      }
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: params.SSH_CREDENTIALS_ID, keyFileVariable: 'SSH_KEY')]) {
          sh '''
            set -eu
            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

            ssh $SSH_OPTS "$DEPLOY_TARGET" \
              "REMOTE_RELEASE_DIR='$REMOTE_RELEASE_DIR' IMAGE_SERVER_NAME='$IMAGE_SERVER_NAME' IMAGE_WEB_NAME='$IMAGE_WEB_NAME' IMAGE_SERVER_LATEST='$IMAGE_SERVER_LATEST' IMAGE_WEB_LATEST='$IMAGE_WEB_LATEST' PYTHON_BASE_IMAGE='$PYTHON_BASE_IMAGE' UV_INDEX_URL='$UV_INDEX_URL' UV_VERSION='$UV_VERSION' NODE_BASE_IMAGE='$NODE_BASE_IMAGE' NGINX_BASE_IMAGE='$NGINX_BASE_IMAGE' NPM_REGISTRY='$NPM_REGISTRY' PROJECT='$PROJECT' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu
cd "$REMOTE_RELEASE_DIR"

echo "=== 清理旧镜像 ==="

# 1. 先清理悬空镜像（无 tag 的中间层）
docker image prune -f 2>/dev/null || true

# 2. 删除该项目的旧版本镜像（保留 latest 和当前运行的版本）
for repo in "${PROJECT}/wild-server" "${PROJECT}/wild-web"; do
  docker images --format '{{.Repository}} {{.Tag}} {{.ID}}' "$repo" 2>/dev/null | while read r tag id; do
    if [ "$tag" = "latest" ]; then continue; fi
    if docker ps --format '{{.Image}}' | grep -qF "$id"; then continue; fi
    echo "  删除旧镜像: $r:$tag ($id)"
    docker rmi "$id" 2>/dev/null || true
  done
done

echo "=== 开始构建新镜像 ==="

docker build \
  --build-arg PYTHON_BASE_IMAGE="$PYTHON_BASE_IMAGE" \
  --build-arg UV_INDEX_URL="$UV_INDEX_URL" \
  --build-arg UV_VERSION="$UV_VERSION" \
  -t "$IMAGE_SERVER_NAME" \
  -t "$IMAGE_SERVER_LATEST" \
  -f wild-server/Dockerfile \
  wild-server

docker build \
  --build-arg NODE_BASE_IMAGE="$NODE_BASE_IMAGE" \
  --build-arg NGINX_BASE_IMAGE="$NGINX_BASE_IMAGE" \
  --build-arg NPM_REGISTRY="$NPM_REGISTRY" \
  -t "$IMAGE_WEB_NAME" \
  -t "$IMAGE_WEB_LATEST" \
  -f wild-web/Dockerfile \
  wild-web
REMOTE_SCRIPT
          '''
        }
      }
    }

    stage('远程部署到生产') {
      when {
        allOf {
          expression { return env.IS_RELEASE_BRANCH == 'true' }
          expression { return params.DEPLOY_ENABLED }
        }
      }
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: params.SSH_CREDENTIALS_ID, keyFileVariable: 'SSH_KEY')]) {
          sh '''
            set -eu
            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

            ssh $SSH_OPTS "$DEPLOY_TARGET" \
              "IMAGE_SERVER_NAME='$IMAGE_SERVER_NAME' IMAGE_WEB_NAME='$IMAGE_WEB_NAME' DEPLOY_DATA_DIR='$DEPLOY_DATA_DIR' DEPLOY_ENV_FILE='$DEPLOY_ENV_FILE' PRESENCE_GEOIP_DB='$PRESENCE_GEOIP_DB' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu

docker network inspect wild-net >/dev/null 2>&1 || docker network create wild-net

# 生产模型配置缺失时必须在删除旧容器前终止，避免用镜像默认值启动坏实例。
if [ ! -f "$DEPLOY_ENV_FILE" ]; then
  echo "ERROR: 未找到生产环境文件 $DEPLOY_ENV_FILE"
  exit 1
fi

echo "=== 部署前校验生产配置与模型连通性 ==="
# 使用本次新镜像和生产 env 做最小真实请求；不输出 Key，也不初始化完整 Agent/RAG。
# 失败时旧容器尚未删除，因此配额、模型 ID、兼容参数或远程网络异常不会造成停机。
timeout -k 10s 90s docker run --rm \
  --env-file "$DEPLOY_ENV_FILE" \
  "$IMAGE_SERVER_NAME" \
  python -c "from pathlib import Path; from config import config; from app.agent.model_client import create_llm; from app.spec.loader import create_embedding_function; kb_root=Path('storage/knowledge_base'); kb_files=list(kb_root.rglob('*.md')); assert (kb_root / 'BLUEPRINT-SPEC-MINIMAL.md').is_file(), 'minimal blueprint spec missing from image'; assert len(kb_files) >= 30, 'incomplete knowledge base in image'; print('knowledge_base_files='+str(len(kb_files))); assert config.chat.name.strip(), 'CHAT__NAME missing'; assert config.chat.api_key.strip(), 'CHAT__API_KEY missing'; embedding_required=config.rag.enabled and not config.rag.allow_hash_fallback; assert (not embedding_required) or (config.embedding.name.strip() and config.embedding.api_key.strip()), 'EMBEDDING config missing while RAG hash fallback is disabled'; print('preflight_model='+config.chat.name); print('preflight_base_url='+(config.chat.base_url or '(default)')); print('preflight_rag_enabled='+str(config.rag.enabled).lower()); print('preflight_embedding='+config.embedding.name); response=create_llm().bind(max_tokens=16).invoke('Reply with WILD_OK only.'); content=response.content if isinstance(response.content, str) else str(response.content); assert content.strip(), 'model returned empty content'; print('model_smoke=ok response_chars='+str(len(content))); embedding=create_embedding_function(config.embedding.api_key, config.embedding.base_url, config.embedding.name, config.rag.allow_hash_fallback) if config.rag.enabled else None; vector=embedding.embed_query('WildAgent deployment smoke') if embedding else []; assert (not embedding) or (vector and isinstance(vector[0], (int, float))), 'embedding returned invalid vector'; print('embedding_smoke=ok dimensions='+str(len(vector)) if embedding else 'embedding_smoke=skipped')"

# 只挂载运行时数据子目录，不挂载整个 /app/storage，避免遮住镜像内置 knowledge_base。
mkdir -p "$DEPLOY_DATA_DIR/scenes" "$DEPLOY_DATA_DIR/sessions" "$DEPLOY_DATA_DIR/chroma" "$DEPLOY_DATA_DIR/assets" "$DEPLOY_DATA_DIR/geoip"

old_server_image="$(docker inspect -f '{{.Config.Image}}' wild-server 2>/dev/null || true)"
old_web_image="$(docker inspect -f '{{.Config.Image}}' wild-web 2>/dev/null || true)"

start_server() {
  server_image="$1"
  docker run -d \
    --name wild-server \
    --restart unless-stopped \
    --network wild-net \
    -p 8000:8000 \
    -v "$DEPLOY_DATA_DIR/scenes:/app/storage/scenes" \
    -v "$DEPLOY_DATA_DIR/sessions:/app/storage/sessions" \
    -v "$DEPLOY_DATA_DIR/chroma:/app/storage/chroma" \
    -v "$DEPLOY_DATA_DIR/assets:/app/storage/assets" \
    -v "$DEPLOY_DATA_DIR/geoip:/app/storage/geoip:ro" \
    --env-file "$DEPLOY_ENV_FILE" \
    -e PRESENCE__GEOIP_DB="$PRESENCE_GEOIP_DB" \
    "$server_image"
}

start_web() {
  web_image="$1"
  docker run -d \
    --name wild-web \
    --restart unless-stopped \
    --network wild-net \
    -p 80:80 \
    "$web_image"
}

rollback_deployment() {
  reason="$1"
  echo "ERROR: $reason"
  echo "--- 新版 wild-server 日志 ---"
  docker logs --tail=100 wild-server 2>&1 || true
  echo "--- 新版 wild-web 日志 ---"
  docker logs --tail=100 wild-web 2>&1 || true
  docker rm -f wild-server wild-web 2>/dev/null || true

  if [ -n "$old_server_image" ]; then
    echo "恢复旧后端镜像: $old_server_image"
    start_server "$old_server_image" || true
  fi
  if [ -n "$old_web_image" ]; then
    echo "恢复旧前端镜像: $old_web_image"
    start_web "$old_web_image" || true
  fi
  exit 1
}

docker rm -f wild-server wild-web 2>/dev/null || true

if ! start_server "$IMAGE_SERVER_NAME"; then
  rollback_deployment "新版 wild-server 容器创建失败"
fi

echo "=== 等待新版 wild-server HTTP 就绪（最多 180 秒） ==="
server_ready=0
attempt=1
while [ "$attempt" -le 60 ]; do
  if [ "$(docker inspect -f '{{.State.Running}}' wild-server 2>/dev/null || true)" != "true" ]; then
    rollback_deployment "新版 wild-server 在启动阶段退出"
  fi

  if docker exec wild-server python -c "import urllib.request; response=urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3); assert response.status == 200" >/dev/null 2>&1; then
    server_ready=1
    echo "wild-server 已就绪（attempt=$attempt）"
    break
  fi

  if [ $((attempt % 10)) -eq 0 ]; then
    echo "wild-server 仍在初始化（attempt=$attempt/60）"
  fi
  attempt=$((attempt + 1))
  sleep 3
done

if [ "$server_ready" -ne 1 ]; then
  rollback_deployment "新版 wild-server 在 180 秒内未就绪"
fi

if ! start_web "$IMAGE_WEB_NAME"; then
  rollback_deployment "新版 wild-web 容器创建失败"
fi

echo "=== 等待新版 wild-web 就绪（最多 40 秒） ==="
web_ready=0
attempt=1
while [ "$attempt" -le 20 ]; do
  if [ "$(docker inspect -f '{{.State.Running}}' wild-web 2>/dev/null || true)" != "true" ]; then
    rollback_deployment "新版 wild-web 在启动阶段退出"
  fi
  if docker exec wild-web wget -q -O /dev/null http://127.0.0.1/ >/dev/null 2>&1; then
    web_ready=1
    echo "wild-web 已就绪（attempt=$attempt）"
    break
  fi
  attempt=$((attempt + 1))
  sleep 2
done

if [ "$web_ready" -ne 1 ]; then
  rollback_deployment "新版 wild-web 在 40 秒内未就绪"
fi
REMOTE_SCRIPT

            echo "=== 检查容器状态 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" \
              "IMAGE_SERVER_NAME='$IMAGE_SERVER_NAME' IMAGE_WEB_NAME='$IMAGE_WEB_NAME' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu

echo "--- 运行中的 wild 容器 ---"
docker ps --filter 'name=wild-' --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

echo ""
echo "--- wild-server 最近日志 ---"
docker logs --tail=30 wild-server 2>&1 || echo "(容器未运行)"

echo ""
echo "--- wild-web 最近日志 ---"
docker logs --tail=30 wild-web 2>&1 || echo "(容器未运行)"

echo ""
if docker ps --format '{{.Names}}' | grep -qx wild-server; then
  echo "wild-server 运行正常"
else
  echo "wild-server 未运行"
  exit 1
fi

if docker ps --format '{{.Names}}' | grep -qx wild-web; then
  echo "wild-web 运行正常"
else
  echo "wild-web 未运行"
  exit 1
fi

actual_server_image=$(docker inspect -f '{{.Config.Image}}' wild-server)
actual_web_image=$(docker inspect -f '{{.Config.Image}}' wild-web)
if [ "$actual_server_image" != "$IMAGE_SERVER_NAME" ]; then
  echo "wild-server 镜像不匹配: actual=$actual_server_image expected=$IMAGE_SERVER_NAME"
  exit 1
fi
if [ "$actual_web_image" != "$IMAGE_WEB_NAME" ]; then
  echo "wild-web 镜像不匹配: actual=$actual_web_image expected=$IMAGE_WEB_NAME"
  exit 1
fi

docker exec wild-server python -c "from config import config; print('model='+config.chat.name); print('base_url='+(config.chat.base_url or '(default)')); print('rag_enabled='+str(config.rag.enabled).lower()); print('embedding='+config.embedding.name); print('hash_fallback='+str(config.rag.allow_hash_fallback).lower()); assert config.chat.name.strip(), 'CHAT__NAME missing'; assert config.chat.api_key.strip(), 'CHAT__API_KEY missing'"
docker exec wild-server python -c "import urllib.request; response=urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=10); body=response.read().decode('utf-8'); print('backend_http_status='+str(response.status)); print('backend_readiness='+body); assert response.status == 200"
REMOTE_SCRIPT

            echo "=== 部署后清理旧镜像 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" \
              "PROJECT='$PROJECT' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu
docker image prune -f 2>/dev/null || true
for repo in "$PROJECT/wild-server" "$PROJECT/wild-web"; do
  docker images --format '{{.Repository}} {{.Tag}} {{.ID}}' "$repo" 2>/dev/null | while read r tag id; do
    if [ "$tag" = 'latest' ]; then continue; fi
    if docker ps --format '{{.Image}}' | grep -qF "$id"; then continue; fi
    docker rmi "$id" 2>/dev/null || true
  done
done
REMOTE_SCRIPT

            echo "部署完成"
          '''
        }
      }
    }
  }

  post {
    always {
      script {
        if (env.REMOTE_RELEASE_DIR && env.IS_PULL_REQUEST != 'true') {
          withCredentials([sshUserPrivateKey(credentialsId: params.SSH_CREDENTIALS_ID, keyFileVariable: 'SSH_KEY')]) {
            sh '''
              set +e
              DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
              SSH_OPTS="-i ${SSH_KEY} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"
              ssh $SSH_OPTS "$DEPLOY_TARGET" "
                case '$REMOTE_RELEASE_DIR' in
                  '$REMOTE_WORK_DIR'/*) rm -rf '$REMOTE_RELEASE_DIR' ;;
                esac
              " >/dev/null 2>&1 || true
              exit 0
            '''
          }
        }
      }
    }
  }
}
