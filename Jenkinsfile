// ============================================================
// WildAgent 部署流水线
//
// 目标服务器：121.41.78.197（阿里云 Alibaba Cloud Linux 3，2C/2G）
// 访问方式：无域名、纯 HTTP（http://121.41.78.197）
//
// 与上一版的差异（旧服务器 39.106.183.13 + www.zzzlew.asia + Let's Encrypt）：
//   1. DEPLOY_SSH_HOST 默认值改为 121.41.78.197，新增 DEPLOY_WEB_PORT；
//   2. 去掉 443 端口发布与 certbot/letsencrypt 挂载（无域名无法签发证书）；
//   3. 新增「远程环境预检」stage：SSH/生产 env/基础镜像可拉取性，失败早于长构建；
//   4. 新增 SSH_AUTH_MODE：默认 password（新机 authorized_keys 为空，key 模式连不上）；
//      日后装好公钥可切回 key；
//   5. 前端就绪判据由「docker top 里有 nginx」改为真实 HTTP 探活。
//
// 旧配置完整保留在仓库根目录的 Jenkinsfile-temp。
// 配套改动：wild-web/nginx.conf 已改为纯 HTTP 单 server 块（旧配置见 nginx.conf-temp）。
// ============================================================

// SSH 凭据绑定：key 模式用私钥文件，password 模式用 Secret text。
// password 模式不依赖 sshpass，走 OpenSSH 的 SSH_ASKPASS + SSH_ASKPASS_REQUIRE=force。
def sshCredentialBindings() {
  if ((params.SSH_AUTH_MODE ?: 'key').trim().toLowerCase() == 'password') {
    return [[$class: 'StringBinding', credentialsId: params.SSH_PASSWORD_CREDENTIAL_ID, variable: 'SSH_PASSWORD']]
  }
  return [[$class: 'SSHUserPrivateKeyBinding', credentialsId: params.SSH_CREDENTIALS_ID, keyFileVariable: 'SSH_KEY']]
}

// 各 stage 共用的 SSH 前置片段：统一导出 DEPLOY_TARGET / SSH_OPTS。
// 这里是 Groovy 单引号字符串，$VAR 一律留给远端 shell 展开。
def sshPrelude() {
  return '''
set -eu
DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
COMMON_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"
if [ "${SSH_AUTH_MODE}" = "password" ]; then
  ASKPASS_FILE="/tmp/wild-agent-ci-askpass.sh"
  trap 'rm -f "$ASKPASS_FILE"' EXIT INT TERM
  umask 077
  cat > "$ASKPASS_FILE" <<'ASKPASS_EOF'
#!/bin/sh
printf '%s\\n' "$SSH_PASSWORD"
ASKPASS_EOF
  chmod 700 "$ASKPASS_FILE"
  export SSH_ASKPASS="$ASKPASS_FILE" SSH_ASKPASS_REQUIRE=force DISPLAY=:0
  SSH_OPTS="$COMMON_OPTS -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1"
else
  if [ -z "${SSH_KEY:-}" ]; then echo "ERROR: key 模式下 SSH_KEY 为空"; exit 1; fi
  SSH_OPTS="$COMMON_OPTS -i ${SSH_KEY} -o IdentitiesOnly=yes -o BatchMode=yes"
fi
export SSH_OPTS DEPLOY_TARGET
'''
}

pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  parameters {
    // ---- 认证 ----
    // 默认 password：当前服务器 /root/.ssh/authorized_keys 为空，key 模式必然连不上。
    // 日后把公钥装到服务器后，可以把这里切回 key。
    choice(name: 'SSH_AUTH_MODE', choices: ['password', 'key'], description: 'SSH 认证方式：password=用 Secret text 凭据里的密码（当前服务器用这个）；key=用 SSH 私钥凭据（需服务器已装公钥）')
    string(name: 'SSH_CREDENTIALS_ID', defaultValue: 'wild-agent-prod-ssh', description: 'key 模式：Jenkins UI 中配置的 SSH 私钥凭据 ID')
    string(name: 'SSH_PASSWORD_CREDENTIAL_ID', defaultValue: 'wild-agent-prod-ssh-password', description: 'password 模式：存放 root 密码的 Jenkins「Secret text」凭据 ID')

    // ---- 部署开关 ----
    booleanParam(name: 'DEPLOY_ENABLED', defaultValue: true, description: 'main/master 分支构建成功后是否部署到服务器')
    booleanParam(name: 'REMOTE_PREFLIGHT_ENABLED', defaultValue: true, description: '是否执行远程环境预检（SSH / 生产 env / 基础镜像可拉取）')
    booleanParam(name: 'REMOTE_VALIDATE_ENABLED', defaultValue: false, description: '是否执行前端编译与后端离线测试；不调用真实模型。当前默认关闭：main 上的 test_design_blocks.py 有 3 个用例仍在按已下线的档位语义断言（2026-10-07 决定先关）')
    booleanParam(name: 'LIVE_PROVIDER_PREFLIGHT_ENABLED', defaultValue: false, description: '部署前是否真实调用 Chat/Embedding；会消耗额度，仅用于手工连通性检查')

    // ---- 目标服务器 ----
    string(name: 'DEPLOY_SSH_USER', defaultValue: 'root', description: '部署服务器 SSH 用户')
    string(name: 'DEPLOY_SSH_HOST', defaultValue: '121.41.78.197', description: '部署服务器地址（新服务器，无域名）')
    string(name: 'DEPLOY_SSH_PORT', defaultValue: '22', description: '部署服务器 SSH 端口')
    string(name: 'DEPLOY_WEB_PORT', defaultValue: '80', description: '宿主机对外暴露的前端端口；无域名场景仅需 80')
    string(name: 'REMOTE_WORK_DIR', defaultValue: '/opt/wild-agent/builds', description: '远程服务器临时构建目录')
    string(name: 'DEPLOY_DATA_DIR', defaultValue: '/opt/wild-agent/storage', description: '远程服务器运行时数据目录')
    string(name: 'DEPLOY_ENV_FILE', defaultValue: '/opt/wild-agent/.env', description: '远程服务器后端容器 env 文件；不存在时部署失败并保留旧容器')
    string(name: 'PRESENCE_GEOIP_DB', defaultValue: '/app/storage/geoip/GeoLite2-City.mmdb', description: '后端容器内 GeoLite2 City 数据库路径')
    string(name: 'DOCKER_REGISTRY_MIRROR', defaultValue: 'https://docker.m.daocloud.io', description: 'Docker Hub 镜像加速地址；新服务器直连 registry-1.docker.io 会超时')
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

    SSH_AUTH_MODE = "${params.SSH_AUTH_MODE}"
    DEPLOY_SSH_USER = "${params.DEPLOY_SSH_USER}"
    DEPLOY_SSH_HOST = "${params.DEPLOY_SSH_HOST}"
    DEPLOY_SSH_PORT = "${params.DEPLOY_SSH_PORT}"
    DEPLOY_WEB_PORT = "${params.DEPLOY_WEB_PORT}"
    REMOTE_WORK_DIR = "${params.REMOTE_WORK_DIR}"
    DEPLOY_DATA_DIR = "${params.DEPLOY_DATA_DIR}"
    DEPLOY_ENV_FILE = "${params.DEPLOY_ENV_FILE}"
    PRESENCE_GEOIP_DB = "${params.PRESENCE_GEOIP_DB}"
    DOCKER_REGISTRY_MIRROR = "${params.DOCKER_REGISTRY_MIRROR}"
    LIVE_PROVIDER_PREFLIGHT_ENABLED = "${params.LIVE_PROVIDER_PREFLIGHT_ENABLED}"
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
          echo "deploy target=${env.DEPLOY_SSH_USER}@${env.DEPLOY_SSH_HOST}:${env.DEPLOY_SSH_PORT} (auth=${env.SSH_AUTH_MODE}), web port=${env.DEPLOY_WEB_PORT}"
          echo "remote release dir=${env.REMOTE_RELEASE_DIR}"
          echo "server image=${env.IMAGE_SERVER_NAME}"
          echo "web image=${env.IMAGE_WEB_NAME}"
        }
      }
    }

    // 新服务器是裸机（无 /opt/wild-agent、无镜像、连不上 Docker Hub），
    // 先把"能不能干活"问清楚，避免 20 分钟后才在 docker build 处失败。
    stage('远程环境预检') {
      when {
        allOf {
          expression { return env.IS_PULL_REQUEST != 'true' }
          expression { return params.REMOTE_PREFLIGHT_ENABLED }
        }
      }
      steps {
        withCredentials(sshCredentialBindings()) {
          sh(sshPrelude() + '''
            echo "=== SSH 连通性 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" "hostname && docker --version && docker compose version 2>/dev/null | head -1"

            echo ""
            echo "=== 远程资源 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" "nproc; free -m | head -2; df -h / | tail -1"

            echo ""
            echo "=== 生产 env 文件（后端容器启动必需）==="
            if ssh $SSH_OPTS "$DEPLOY_TARGET" "test -f '$DEPLOY_ENV_FILE'"; then
              echo "OK: $DEPLOY_ENV_FILE 存在（内容不打印）"
            else
              echo "ERROR: 远程缺少 $DEPLOY_ENV_FILE"
              echo "  修复: 在服务器创建该文件，键名参考仓库内 wild-server/.env.example"
              echo "        至少需要 CHAT__NAME / CHAT__API_KEY / EMBEDDING__NAME / EMBEDDING__API_KEY"
              exit 1
            fi

            echo ""
            echo "=== 基础镜像可拉取性（docker build 的前提）==="
            image_fail=0
            for img in "$PYTHON_BASE_IMAGE" "$NODE_BASE_IMAGE" "$NGINX_BASE_IMAGE"; do
              if ssh $SSH_OPTS "$DEPLOY_TARGET" "timeout 180 docker pull -q '$img' >/dev/null 2>&1"; then
                echo "OK   $img"
              else
                echo "FAIL $img"
                image_fail=1
              fi
            done
            if [ "$image_fail" -ne 0 ]; then
              echo ""
              echo "ERROR: 远程服务器无法拉取基础镜像。"
              echo "  原因: 新机器未配置镜像加速，直连 registry-1.docker.io 超时。"
              echo "  修复: 在远程服务器写入 registry-mirrors 后重启 docker，例如"
              echo "        /etc/docker/daemon.json -> {\"registry-mirrors\": [\"$DOCKER_REGISTRY_MIRROR\"]}"
              echo "        systemctl restart docker"
              exit 1
            fi

            echo ""
            echo "预检通过"
          ''')
        }
      }
    }

    stage('上传源码到远程服务器') {
      when {
        expression { return env.IS_PULL_REQUEST != 'true' }
      }
      steps {
        withCredentials(sshCredentialBindings()) {
          sh(sshPrelude() + '''
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
          ''')
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
        withCredentials(sshCredentialBindings()) {
          sh(sshPrelude() + '''
            ssh $SSH_OPTS "$DEPLOY_TARGET" \\
              "REMOTE_RELEASE_DIR='$REMOTE_RELEASE_DIR' NODE_BASE_IMAGE='$NODE_BASE_IMAGE' NPM_REGISTRY='$NPM_REGISTRY' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu
docker run --rm \\
  -e NPM_REGISTRY="$NPM_REGISTRY" \\
  -v "$REMOTE_RELEASE_DIR:/repo" \\
  -w /repo/wild-web \\
  "$NODE_BASE_IMAGE" \\
  sh -lc 'npm config set registry "$NPM_REGISTRY" && npm ci && npm run build'
REMOTE_SCRIPT
          ''')
        }
      }
    }

    stage('远程后端离线测试') {
      when {
        allOf {
          expression { return env.IS_PULL_REQUEST != 'true' }
          expression { return params.REMOTE_VALIDATE_ENABLED }
        }
      }
      steps {
        withCredentials(sshCredentialBindings()) {
          sh(sshPrelude() + '''
            ssh $SSH_OPTS "$DEPLOY_TARGET" \\
              "REMOTE_RELEASE_DIR='$REMOTE_RELEASE_DIR' PYTHON_BASE_IMAGE='$PYTHON_BASE_IMAGE' UV_INDEX_URL='$UV_INDEX_URL' UV_VERSION='$UV_VERSION' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu
cd "$REMOTE_RELEASE_DIR/wild-server"
docker run --rm \\
  -e PYTHONDONTWRITEBYTECODE=1 \\
  -e UV_INDEX_URL="$UV_INDEX_URL" \\
  -e UV_VERSION="$UV_VERSION" \\
  -e CHAT__NAME=ci-dummy-chat \\
  -e CHAT__API_KEY=ci-placeholder \\
  -e CHAT__BASE_URL=http://127.0.0.1:9/v1 \\
  -e RAG__ALLOW_HASH_FALLBACK=true \\
  -e RAG__PERSIST_DIR=/tmp/wild-agent-ci-chroma \\
  -v "$PWD:/app" \\
  -w /app \\
  "$PYTHON_BASE_IMAGE" \\
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
          ''')
        }
      }
    }

    stage('远程构建 Docker 镜像') {
      when {
        expression { return env.IS_RELEASE_BRANCH == 'true' }
      }
      steps {
        withCredentials(sshCredentialBindings()) {
          sh(sshPrelude() + '''
            ssh $SSH_OPTS "$DEPLOY_TARGET" \\
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

docker build \\
  --build-arg PYTHON_BASE_IMAGE="$PYTHON_BASE_IMAGE" \\
  --build-arg UV_INDEX_URL="$UV_INDEX_URL" \\
  --build-arg UV_VERSION="$UV_VERSION" \\
  -t "$IMAGE_SERVER_NAME" \\
  -t "$IMAGE_SERVER_LATEST" \\
  -f wild-server/Dockerfile \\
  wild-server

docker build \\
  --build-arg NODE_BASE_IMAGE="$NODE_BASE_IMAGE" \\
  --build-arg NGINX_BASE_IMAGE="$NGINX_BASE_IMAGE" \\
  --build-arg NPM_REGISTRY="$NPM_REGISTRY" \\
  -t "$IMAGE_WEB_NAME" \\
  -t "$IMAGE_WEB_LATEST" \\
  -f wild-web/Dockerfile \\
  .
REMOTE_SCRIPT
          ''')
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
        withCredentials(sshCredentialBindings()) {
          sh(sshPrelude() + '''
            ssh $SSH_OPTS "$DEPLOY_TARGET" \\
              "IMAGE_SERVER_NAME='$IMAGE_SERVER_NAME' IMAGE_WEB_NAME='$IMAGE_WEB_NAME' DEPLOY_DATA_DIR='$DEPLOY_DATA_DIR' DEPLOY_ENV_FILE='$DEPLOY_ENV_FILE' DEPLOY_WEB_PORT='$DEPLOY_WEB_PORT' PRESENCE_GEOIP_DB='$PRESENCE_GEOIP_DB' LIVE_PROVIDER_PREFLIGHT_ENABLED='$LIVE_PROVIDER_PREFLIGHT_ENABLED' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu

docker network inspect wild-net >/dev/null 2>&1 || docker network create wild-net

# 生产运行时配置文件缺失时必须在删除旧容器前终止。
if [ ! -f "$DEPLOY_ENV_FILE" ]; then
  echo "ERROR: 未找到生产环境文件 $DEPLOY_ENV_FILE"
  exit 1
fi

echo "=== 部署前校验镜像与知识库（默认离线） ==="
run_deployment_preflight() {
  timeout -k 10s 90s docker run --rm \\
    --env-file "$DEPLOY_ENV_FILE" \\
    "$IMAGE_SERVER_NAME" \\
    python -m scripts.deploy.deployment_preflight "$@"
}

if [ "$LIVE_PROVIDER_PREFLIGHT_ENABLED" = "true" ]; then
  echo "已启用真实 Chat/Embedding 冒烟；本次检查会消耗供应商额度。"
  run_deployment_preflight --live-providers
else
  run_deployment_preflight
fi

# 只挂载运行时数据子目录，不挂载整个 /app/storage，避免遮住镜像内置 knowledge_base。
mkdir -p "$DEPLOY_DATA_DIR/scenes" "$DEPLOY_DATA_DIR/sessions" "$DEPLOY_DATA_DIR/chroma" "$DEPLOY_DATA_DIR/assets" "$DEPLOY_DATA_DIR/geoip"

old_server_image="$(docker inspect -f '{{.Config.Image}}' wild-server 2>/dev/null || true)"
old_web_image="$(docker inspect -f '{{.Config.Image}}' wild-web 2>/dev/null || true)"

start_server() {
  server_image="$1"
  docker run -d \\
    --name wild-server \\
    --restart unless-stopped \\
    --network wild-net \\
    -p 8000:8000 \\
    -v "$DEPLOY_DATA_DIR/scenes:/app/storage/scenes" \\
    -v "$DEPLOY_DATA_DIR/sessions:/app/storage/sessions" \\
    -v "$DEPLOY_DATA_DIR/chroma:/app/storage/chroma" \\
    -v "$DEPLOY_DATA_DIR/assets:/app/storage/assets" \\
    -v "$DEPLOY_DATA_DIR/geoip:/app/storage/geoip:ro" \\
    -v "$DEPLOY_ENV_FILE:/app/runtime-config/.env" \\
    --env-file "$DEPLOY_ENV_FILE" \\
    -e WILD_RUNTIME_ENV_FILE=/app/runtime-config/.env \\
    -e WILD_RUNTIME_ENV_PERSISTENT=true \\
    -e WILD_RUNTIME_ENV_HOST_PATH="$DEPLOY_ENV_FILE" \\
    -e PRESENCE__GEOIP_DB="$PRESENCE_GEOIP_DB" \\
    "$server_image"
}

# 无域名部署：nginx.conf 已改为纯 HTTP，不再需要 443 与 Let's Encrypt 证书挂载。
start_web() {
  web_image="$1"
  docker run -d \\
    --name wild-web \\
    --restart unless-stopped \\
    --network wild-net \\
    -p "$DEPLOY_WEB_PORT":80 \\
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
  # 纯 HTTP 部署下直接打 nginx 自身；容器内 busybox wget 即可，不再依赖 301 特判。
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
            ssh $SSH_OPTS "$DEPLOY_TARGET" \\
              "IMAGE_SERVER_NAME='$IMAGE_SERVER_NAME' IMAGE_WEB_NAME='$IMAGE_WEB_NAME' DEPLOY_WEB_PORT='$DEPLOY_WEB_PORT' DEPLOY_SSH_HOST='$DEPLOY_SSH_HOST' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu

echo "--- 运行中的 wild 容器 ---"
docker ps --filter 'name=wild-' --format 'table {{.Names}}	{{.Image}}	{{.Status}}	{{.Ports}}'

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

# 无域名场景下，判据是"用 IP 当 Host 也能拿到 200"，而不是只看到 nginx 进程在跑。
echo ""
echo "--- 前端 HTTP 可达性（localhost:${DEPLOY_WEB_PORT}） ---"
code_local=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://127.0.0.1:${DEPLOY_WEB_PORT}/" || echo 000)
echo "GET / -> $code_local"
code_ip=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 -H "Host: ${DEPLOY_SSH_HOST}" "http://127.0.0.1:${DEPLOY_WEB_PORT}/" || echo 000)
echo "GET / (Host: ${DEPLOY_SSH_HOST}) -> $code_ip"
if [ "$code_local" != "200" ] || [ "$code_ip" != "200" ]; then
  echo "ERROR: 前端 HTTP 探活未通过（期望 200/200）"
  exit 1
fi

echo ""
echo "--- 前端 API 反向代理可达性 ---"
# 用 /api/config/llm（无需鉴权的真实路由）而不是状态码判 200：
# 后端健康检查在 /health/ready，不在 /api/ 下；而不存在的路径会被 SPA 的
# try_files 兜底成 index.html 200，只看状态码会假通过。
api_body=$(curl -s --max-time 8 "http://127.0.0.1:${DEPLOY_WEB_PORT}/api/config/llm" || true)
case "$api_body" in
  *storage_path*)
    echo "GET /api/config/llm -> 反代生效（已拿到后端 JSON）"
    ;;
  *)
    echo "ERROR: /api/ 反向代理未打通（nginx -> wild-server:8000），实际响应: $(echo "$api_body" | head -c 200)"
    exit 1
    ;;
esac

docker exec wild-server python -c "from config import config; print('model='+config.chat.name); print('model_configured='+str(bool(config.chat.name.strip() and config.chat.api_key.strip())).lower()); print('base_url='+(config.chat.base_url or '(default)')); print('rag_enabled='+str(config.rag.enabled).lower()); print('embedding='+config.embedding.name); print('hash_fallback='+str(config.rag.allow_hash_fallback).lower())"
docker exec wild-server python -c "import urllib.request; response=urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=10); body=response.read().decode('utf-8'); print('backend_http_status='+str(response.status)); print('backend_readiness='+body); assert response.status == 200"
docker exec wild-server python -c "import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/config/llm', timeout=10)); print('runtime_config_path='+data['storage_path']); print('runtime_config_host_path='+(data.get('host_storage_path') or '(unknown)')); print('runtime_config_persistent='+str(data['persistent']).lower()); assert data['storage_path']=='/app/runtime-config/.env'; assert data['persistent'] is True"
REMOTE_SCRIPT

            echo "=== 部署后清理旧镜像 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" \\
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

            echo "部署完成；访问入口：http://$DEPLOY_SSH_HOST:${DEPLOY_WEB_PORT}/"
          ''')
        }
      }
    }
  }

  post {
    always {
      script {
        // 清掉 password 模式可能残留的 askpass 临时文件
        sh 'rm -f /tmp/wild-agent-ci-askpass.sh || true'

        if (env.REMOTE_RELEASE_DIR && env.IS_PULL_REQUEST != 'true') {
          withCredentials(sshCredentialBindings()) {
            sh(sshPrelude() + '''
              set +e
              ssh $SSH_OPTS "$DEPLOY_TARGET" "
                case '$REMOTE_RELEASE_DIR' in
                  '$REMOTE_WORK_DIR'/*) rm -rf '$REMOTE_RELEASE_DIR' ;;
                esac
              " >/dev/null 2>&1 || true
              exit 0
            ''')
          }
        }
      }
    }
  }
}
