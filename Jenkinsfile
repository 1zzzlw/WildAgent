pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  parameters {
    string(name: 'REGISTRY_IMAGE', defaultValue: '', description: '镜像仓库路径；留空时从 GitHub remote 自动推导为 ghcr.io/<owner>/<repo>')
    string(name: 'DOCKER_CREDENTIALS_ID', defaultValue: 'github-container-registry', description: 'Jenkins 用户名密码凭据 ID；GitHub/GHCR 建议使用 GitHub 用户名 + PAT')
    string(name: 'SSH_CREDENTIALS_ID', defaultValue: 'wild-agent-prod-ssh', description: 'Jenkins SSH 私钥凭据 ID，用于远程部署')
    booleanParam(name: 'DEPLOY_ENABLED', defaultValue: true, description: 'main/master 分支构建成功后是否部署到服务器')
    string(name: 'DEPLOY_SSH_USER', defaultValue: 'root', description: '部署服务器 SSH 用户')
    string(name: 'DEPLOY_SSH_HOST', defaultValue: '39.106.183.13', description: '部署服务器地址')
    string(name: 'DEPLOY_SSH_PORT', defaultValue: '22', description: '部署服务器 SSH 端口')
    string(name: 'DEPLOY_DATA_DIR', defaultValue: '/opt/wild-agent/storage', description: '服务器运行时数据目录')
  }

  environment {
    PROJECT = 'wild-agent'
    NPM_REGISTRY = 'https://registry.npmmirror.com'
    UV_INDEX_URL = 'https://mirrors.aliyun.com/pypi/simple/'
    PYTHON_BASE_IMAGE = 'python:3.12-slim'
    NODE_BASE_IMAGE = 'node:22-alpine'
    NGINX_BASE_IMAGE = 'nginx:alpine'
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

          def registryImage = params.REGISTRY_IMAGE?.trim()
          if (!registryImage) {
            def gitUrl = sh(returnStdout: true, script: 'git config --get remote.origin.url || true').trim()
            def githubMatch = gitUrl =~ /github\.com[:\/]([^\/:]+)\/([^\/]+?)(?:\.git)?$/
            if (githubMatch) {
              registryImage = "ghcr.io/${githubMatch[0][1]}/${githubMatch[0][2]}".toLowerCase()
            }
          }

          if (env.IS_RELEASE_BRANCH == 'true' && !registryImage) {
            error('main/master 构建需要设置 REGISTRY_IMAGE，或确保 remote.origin.url 是 GitHub 仓库地址')
          }

          env.REGISTRY_IMAGE = (registryImage ?: 'local/wild-agent').toLowerCase()
          env.REGISTRY = env.REGISTRY_IMAGE.split('/')[0]
          env.IMAGE_SERVER_NAME = "${env.REGISTRY_IMAGE}/wild-server:${env.REF_SLUG}-${env.COMMIT_SHA}"
          env.IMAGE_WEB_NAME = "${env.REGISTRY_IMAGE}/wild-web:${env.REF_SLUG}-${env.COMMIT_SHA}"
          env.IMAGE_SERVER_LATEST = "${env.REGISTRY_IMAGE}/wild-server:latest"
          env.IMAGE_WEB_LATEST = "${env.REGISTRY_IMAGE}/wild-web:latest"

          echo "branch=${env.BUILD_BRANCH}, pull_request=${env.IS_PULL_REQUEST}, release=${env.IS_RELEASE_BRANCH}, commit=${env.COMMIT_SHORT}"
          echo "server image=${env.IMAGE_SERVER_NAME}"
          echo "web image=${env.IMAGE_WEB_NAME}"
        }
      }
    }

    stage('前端编译检查') {
      steps {
        sh '''
          set -eu
          docker run --rm \
            -e NPM_REGISTRY="$NPM_REGISTRY" \
            -v "$PWD/wild-web:/app" \
            -w /app \
            "$NODE_BASE_IMAGE" \
            sh -lc 'npm config set registry "$NPM_REGISTRY" && npm ci && npm run build'
        '''
      }
      post {
        success {
          archiveArtifacts artifacts: 'wild-web/dist/**', fingerprint: true, allowEmptyArchive: false
        }
      }
    }

    stage('后端语法检查') {
      steps {
        sh '''
          set -eu
          docker run --rm \
            -e PYTHONDONTWRITEBYTECODE=1 \
            -e UV_INDEX_URL="$UV_INDEX_URL" \
            -v "$PWD/wild-server:/app" \
            -w /app \
            "$PYTHON_BASE_IMAGE" \
            sh -lc '
              pip install --no-cache-dir uv -i "$UV_INDEX_URL" --trusted-host mirrors.aliyun.com
              python -m compileall app/
              python -c "import ast; ast.parse(open(\"main.py\", encoding=\"utf-8\").read()); print(\"main.py OK\")"
              uv lock --check 2>/dev/null || echo "uv.lock 不是最新的，但不阻塞 CI"
            '
        '''
      }
    }

    stage('Docker 登录') {
      when {
        expression { return env.IS_RELEASE_BRANCH == 'true' }
      }
      steps {
        withCredentials([usernamePassword(credentialsId: params.DOCKER_CREDENTIALS_ID, usernameVariable: 'REGISTRY_USER', passwordVariable: 'REGISTRY_PASSWORD')]) {
          sh '''
            set -eu
            printf '%s' "$REGISTRY_PASSWORD" | docker login --username "$REGISTRY_USER" --password-stdin "$REGISTRY"
          '''
        }
      }
    }

    stage('构建后端镜像') {
      when {
        expression { return env.IS_RELEASE_BRANCH == 'true' }
      }
      steps {
        sh '''
          set -eu
          docker build \
            --build-arg PYTHON_BASE_IMAGE="$PYTHON_BASE_IMAGE" \
            --build-arg UV_INDEX_URL="$UV_INDEX_URL" \
            -t "$IMAGE_SERVER_NAME" \
            -t "$IMAGE_SERVER_LATEST" \
            -f wild-server/Dockerfile \
            wild-server
          docker push "$IMAGE_SERVER_NAME"
          docker push "$IMAGE_SERVER_LATEST"
          docker rmi "$IMAGE_SERVER_NAME" "$IMAGE_SERVER_LATEST" || true
        '''
      }
    }

    stage('构建前端镜像') {
      when {
        expression { return env.IS_RELEASE_BRANCH == 'true' }
      }
      steps {
        sh '''
          set -eu
          docker build \
            --build-arg NODE_BASE_IMAGE="$NODE_BASE_IMAGE" \
            --build-arg NGINX_BASE_IMAGE="$NGINX_BASE_IMAGE" \
            --build-arg NPM_REGISTRY="$NPM_REGISTRY" \
            -t "$IMAGE_WEB_NAME" \
            -t "$IMAGE_WEB_LATEST" \
            -f wild-web/Dockerfile \
            wild-web
          docker push "$IMAGE_WEB_NAME"
          docker push "$IMAGE_WEB_LATEST"
          docker rmi "$IMAGE_WEB_NAME" "$IMAGE_WEB_LATEST" || true
        '''
      }
    }

    stage('部署到生产') {
      when {
        allOf {
          expression { return env.IS_RELEASE_BRANCH == 'true' }
          expression { return params.DEPLOY_ENABLED }
        }
      }
      steps {
        withCredentials([
          usernamePassword(credentialsId: params.DOCKER_CREDENTIALS_ID, usernameVariable: 'REGISTRY_USER', passwordVariable: 'REGISTRY_PASSWORD'),
          sshUserPrivateKey(credentialsId: params.SSH_CREDENTIALS_ID, keyFileVariable: 'SSH_KEY')
        ]) {
          sh '''
            set -eu

            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

            echo "=== 测试 SSH 连接 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" "hostname && docker --version"

            echo "=== 登录远程 Docker Registry ==="
            printf '%s' "$REGISTRY_PASSWORD" | ssh $SSH_OPTS "$DEPLOY_TARGET" "docker login --username '$REGISTRY_USER' --password-stdin '$REGISTRY'"

            echo "=== 拉取并重建容器 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" /bin/sh <<EOF
set -eu

docker pull "$IMAGE_SERVER_NAME"
docker pull "$IMAGE_WEB_NAME"

docker network inspect wild-net >/dev/null 2>&1 || docker network create wild-net
docker rm -f wild-server wild-web 2>/dev/null || true

# 只挂载运行时数据目录，不挂载整个 /app/storage，避免遮住镜像内置 knowledge_base。
mkdir -p "$DEPLOY_DATA_DIR/scenes" "$DEPLOY_DATA_DIR/sessions" "$DEPLOY_DATA_DIR/chroma"

docker run -d \
  --name wild-server \
  --restart unless-stopped \
  --network wild-net \
  -p 8000:8000 \
  -v "$DEPLOY_DATA_DIR/scenes:/app/storage/scenes" \
  -v "$DEPLOY_DATA_DIR/sessions:/app/storage/sessions" \
  -v "$DEPLOY_DATA_DIR/chroma:/app/storage/chroma" \
  -e CHAT__NAME="${CHAT__NAME:-}" \
  -e CHAT__API_KEY="${CHAT__API_KEY:-}" \
  -e CHAT__BASE_URL="${CHAT__BASE_URL:-}" \
  -e EMBEDDING__NAME="${EMBEDDING__NAME:-}" \
  -e EMBEDDING__API_KEY="${EMBEDDING__API_KEY:-}" \
  -e EMBEDDING__BASE_URL="${EMBEDDING__BASE_URL:-}" \
  -e RERANK__NAME="${RERANK__NAME:-}" \
  -e RERANK__API_KEY="${RERANK__API_KEY:-}" \
  -e RERANK__BASE_URL="${RERANK__BASE_URL:-}" \
  "$IMAGE_SERVER_NAME"

docker run -d \
  --name wild-web \
  --restart unless-stopped \
  --network wild-net \
  -p 80:80 \
  "$IMAGE_WEB_NAME"
EOF

            echo "=== 等待容器启动 ==="
            sleep 5

            echo "=== 检查容器状态 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" /bin/sh <<'EOF'
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
EOF

            echo "部署完成"
          '''
        }
      }
    }
  }

  post {
    always {
      sh '''
        docker logout "$REGISTRY" >/dev/null 2>&1 || true
      '''
    }
  }
}
