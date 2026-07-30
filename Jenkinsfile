pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  parameters {
    string(name: 'SSH_CREDENTIALS_ID', defaultValue: 'wild-agent-prod-ssh', description: 'Jenkins SSH 私钥凭据 ID，用于连接远程 Docker 服务器')
    booleanParam(name: 'DEPLOY_ENABLED', defaultValue: true, description: 'main/master 分支构建成功后是否部署到服务器')
    booleanParam(name: 'REMOTE_VALIDATE_ENABLED', defaultValue: true, description: '是否在远程服务器用 Docker 执行前后端验证')
    string(name: 'DEPLOY_SSH_USER', defaultValue: 'root', description: '部署服务器 SSH 用户')
    string(name: 'DEPLOY_SSH_HOST', defaultValue: '39.106.183.13', description: '部署服务器地址')
    string(name: 'DEPLOY_SSH_PORT', defaultValue: '22', description: '部署服务器 SSH 端口')
    string(name: 'REMOTE_WORK_DIR', defaultValue: '/opt/wild-agent/builds', description: '远程服务器临时构建目录')
    string(name: 'DEPLOY_DATA_DIR', defaultValue: '/opt/wild-agent/storage', description: '远程服务器运行时数据目录')
    string(name: 'DEPLOY_ENV_FILE', defaultValue: '/opt/wild-agent/.env', description: '远程服务器后端容器 env 文件；不存在时仍会启动')
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

          def safeJobName = (env.JOB_NAME ?: env.PROJECT).replaceAll(/[^A-Za-z0-9_.-]+/, '-').toLowerCase()
          env.REMOTE_WORK_DIR = params.REMOTE_WORK_DIR
          env.REMOTE_RELEASE_DIR = "${params.REMOTE_WORK_DIR}/${safeJobName}-${env.BUILD_NUMBER}-${env.COMMIT_SHORT}"
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
            fix_ssh_key_permissions() {
              chmod 600 "$SSH_KEY" 2>/dev/null || true

              if command -v powershell.exe >/dev/null 2>&1; then
                SSH_KEY_PATH="$SSH_KEY" powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command '
$path = $env:SSH_KEY_PATH
$acl = Get-Acl -LiteralPath $path
$acl.SetAccessRuleProtection($true, $false)
foreach ($rule in @($acl.Access)) {
  [void]$acl.RemoveAccessRuleAll($rule)
}
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($current, "FullControl", "Allow")
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $path -AclObject $acl
' >/dev/null 2>&1 || true
              fi

              if command -v cmd.exe >/dev/null 2>&1; then
                CURRENT_USER="$(whoami 2>/dev/null || printf '%s' "${USERNAME:-}")"
                cmd.exe /c icacls "$SSH_KEY" /inheritance:r >/dev/null 2>&1 || true
                cmd.exe /c icacls "$SSH_KEY" /remove:g "*S-1-5-11" "*S-1-5-32-545" "*S-1-1-0" "NT AUTHORITY\\Authenticated Users" "BUILTIN\\Users" "Everyone" >/dev/null 2>&1 || true
                if [ -n "$CURRENT_USER" ]; then
                  cmd.exe /c icacls "$SSH_KEY" /grant:r "$CURRENT_USER:F" >/dev/null 2>&1 || true
                fi
              fi
            }
            fix_ssh_key_permissions

            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

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
            fix_ssh_key_permissions() {
              chmod 600 "$SSH_KEY" 2>/dev/null || true

              if command -v powershell.exe >/dev/null 2>&1; then
                SSH_KEY_PATH="$SSH_KEY" powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command '
$path = $env:SSH_KEY_PATH
$acl = Get-Acl -LiteralPath $path
$acl.SetAccessRuleProtection($true, $false)
foreach ($rule in @($acl.Access)) {
  [void]$acl.RemoveAccessRuleAll($rule)
}
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($current, "FullControl", "Allow")
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $path -AclObject $acl
' >/dev/null 2>&1 || true
              fi

              if command -v cmd.exe >/dev/null 2>&1; then
                CURRENT_USER="$(whoami 2>/dev/null || printf '%s' "${USERNAME:-}")"
                cmd.exe /c icacls "$SSH_KEY" /inheritance:r >/dev/null 2>&1 || true
                cmd.exe /c icacls "$SSH_KEY" /remove:g "*S-1-5-11" "*S-1-5-32-545" "*S-1-1-0" "NT AUTHORITY\\Authenticated Users" "BUILTIN\\Users" "Everyone" >/dev/null 2>&1 || true
                if [ -n "$CURRENT_USER" ]; then
                  cmd.exe /c icacls "$SSH_KEY" /grant:r "$CURRENT_USER:F" >/dev/null 2>&1 || true
                fi
              fi
            }
            fix_ssh_key_permissions

            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

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
            fix_ssh_key_permissions() {
              chmod 600 "$SSH_KEY" 2>/dev/null || true

              if command -v powershell.exe >/dev/null 2>&1; then
                SSH_KEY_PATH="$SSH_KEY" powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command '
$path = $env:SSH_KEY_PATH
$acl = Get-Acl -LiteralPath $path
$acl.SetAccessRuleProtection($true, $false)
foreach ($rule in @($acl.Access)) {
  [void]$acl.RemoveAccessRuleAll($rule)
}
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($current, "FullControl", "Allow")
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $path -AclObject $acl
' >/dev/null 2>&1 || true
              fi

              if command -v cmd.exe >/dev/null 2>&1; then
                CURRENT_USER="$(whoami 2>/dev/null || printf '%s' "${USERNAME:-}")"
                cmd.exe /c icacls "$SSH_KEY" /inheritance:r >/dev/null 2>&1 || true
                cmd.exe /c icacls "$SSH_KEY" /remove:g "*S-1-5-11" "*S-1-5-32-545" "*S-1-1-0" "NT AUTHORITY\\Authenticated Users" "BUILTIN\\Users" "Everyone" >/dev/null 2>&1 || true
                if [ -n "$CURRENT_USER" ]; then
                  cmd.exe /c icacls "$SSH_KEY" /grant:r "$CURRENT_USER:F" >/dev/null 2>&1 || true
                fi
              fi
            }
            fix_ssh_key_permissions

            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

            ssh $SSH_OPTS "$DEPLOY_TARGET" \
              "REMOTE_RELEASE_DIR='$REMOTE_RELEASE_DIR' PYTHON_BASE_IMAGE='$PYTHON_BASE_IMAGE' UV_INDEX_URL='$UV_INDEX_URL' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu
cd "$REMOTE_RELEASE_DIR/wild-server"
docker run --rm \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e UV_INDEX_URL="$UV_INDEX_URL" \
  -v "$PWD:/app" \
  -w /app \
  "$PYTHON_BASE_IMAGE" \
  sh -lc '
    pip install --no-cache-dir uv -i "$UV_INDEX_URL" --trusted-host mirrors.aliyun.com
    python -m compileall app/
    python -m py_compile main.py
    uv lock --check 2>/dev/null || echo "uv.lock 不是最新的，但不阻塞 CI"
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
            fix_ssh_key_permissions() {
              chmod 600 "$SSH_KEY" 2>/dev/null || true

              if command -v powershell.exe >/dev/null 2>&1; then
                SSH_KEY_PATH="$SSH_KEY" powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command '
$path = $env:SSH_KEY_PATH
$acl = Get-Acl -LiteralPath $path
$acl.SetAccessRuleProtection($true, $false)
foreach ($rule in @($acl.Access)) {
  [void]$acl.RemoveAccessRuleAll($rule)
}
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($current, "FullControl", "Allow")
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $path -AclObject $acl
' >/dev/null 2>&1 || true
              fi

              if command -v cmd.exe >/dev/null 2>&1; then
                CURRENT_USER="$(whoami 2>/dev/null || printf '%s' "${USERNAME:-}")"
                cmd.exe /c icacls "$SSH_KEY" /inheritance:r >/dev/null 2>&1 || true
                cmd.exe /c icacls "$SSH_KEY" /remove:g "*S-1-5-11" "*S-1-5-32-545" "*S-1-1-0" "NT AUTHORITY\\Authenticated Users" "BUILTIN\\Users" "Everyone" >/dev/null 2>&1 || true
                if [ -n "$CURRENT_USER" ]; then
                  cmd.exe /c icacls "$SSH_KEY" /grant:r "$CURRENT_USER:F" >/dev/null 2>&1 || true
                fi
              fi
            }
            fix_ssh_key_permissions

            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

            ssh $SSH_OPTS "$DEPLOY_TARGET" \
              "REMOTE_RELEASE_DIR='$REMOTE_RELEASE_DIR' IMAGE_SERVER_NAME='$IMAGE_SERVER_NAME' IMAGE_WEB_NAME='$IMAGE_WEB_NAME' IMAGE_SERVER_LATEST='$IMAGE_SERVER_LATEST' IMAGE_WEB_LATEST='$IMAGE_WEB_LATEST' PYTHON_BASE_IMAGE='$PYTHON_BASE_IMAGE' UV_INDEX_URL='$UV_INDEX_URL' NODE_BASE_IMAGE='$NODE_BASE_IMAGE' NGINX_BASE_IMAGE='$NGINX_BASE_IMAGE' NPM_REGISTRY='$NPM_REGISTRY' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu
cd "$REMOTE_RELEASE_DIR"

docker build \
  --build-arg PYTHON_BASE_IMAGE="$PYTHON_BASE_IMAGE" \
  --build-arg UV_INDEX_URL="$UV_INDEX_URL" \
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
            fix_ssh_key_permissions() {
              chmod 600 "$SSH_KEY" 2>/dev/null || true

              if command -v powershell.exe >/dev/null 2>&1; then
                SSH_KEY_PATH="$SSH_KEY" powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command '
$path = $env:SSH_KEY_PATH
$acl = Get-Acl -LiteralPath $path
$acl.SetAccessRuleProtection($true, $false)
foreach ($rule in @($acl.Access)) {
  [void]$acl.RemoveAccessRuleAll($rule)
}
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($current, "FullControl", "Allow")
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $path -AclObject $acl
' >/dev/null 2>&1 || true
              fi

              if command -v cmd.exe >/dev/null 2>&1; then
                CURRENT_USER="$(whoami 2>/dev/null || printf '%s' "${USERNAME:-}")"
                cmd.exe /c icacls "$SSH_KEY" /inheritance:r >/dev/null 2>&1 || true
                cmd.exe /c icacls "$SSH_KEY" /remove:g "*S-1-5-11" "*S-1-5-32-545" "*S-1-1-0" "NT AUTHORITY\\Authenticated Users" "BUILTIN\\Users" "Everyone" >/dev/null 2>&1 || true
                if [ -n "$CURRENT_USER" ]; then
                  cmd.exe /c icacls "$SSH_KEY" /grant:r "$CURRENT_USER:F" >/dev/null 2>&1 || true
                fi
              fi
            }
            fix_ssh_key_permissions

            DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
            SSH_OPTS="-i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"

            ssh $SSH_OPTS "$DEPLOY_TARGET" \
              "IMAGE_SERVER_NAME='$IMAGE_SERVER_NAME' IMAGE_WEB_NAME='$IMAGE_WEB_NAME' DEPLOY_DATA_DIR='$DEPLOY_DATA_DIR' DEPLOY_ENV_FILE='$DEPLOY_ENV_FILE' /bin/sh -s" <<'REMOTE_SCRIPT'
set -eu

docker network inspect wild-net >/dev/null 2>&1 || docker network create wild-net
docker rm -f wild-server wild-web 2>/dev/null || true

# 只挂载运行时数据目录，不挂载整个 /app/storage，避免遮住镜像内置 knowledge_base。
mkdir -p "$DEPLOY_DATA_DIR/scenes" "$DEPLOY_DATA_DIR/sessions" "$DEPLOY_DATA_DIR/chroma"

ENV_FILE_ARGS=""
if [ -f "$DEPLOY_ENV_FILE" ]; then
  ENV_FILE_ARGS="--env-file $DEPLOY_ENV_FILE"
else
  echo "WARN: 未找到 $DEPLOY_ENV_FILE，后端将使用镜像默认环境变量"
fi

docker run -d \
  --name wild-server \
  --restart unless-stopped \
  --network wild-net \
  -p 8000:8000 \
  -v "$DEPLOY_DATA_DIR/scenes:/app/storage/scenes" \
  -v "$DEPLOY_DATA_DIR/sessions:/app/storage/sessions" \
  -v "$DEPLOY_DATA_DIR/chroma:/app/storage/chroma" \
  $ENV_FILE_ARGS \
  "$IMAGE_SERVER_NAME"

docker run -d \
  --name wild-web \
  --restart unless-stopped \
  --network wild-net \
  -p 80:80 \
  "$IMAGE_WEB_NAME"
REMOTE_SCRIPT

            echo "=== 等待容器启动 ==="
            sleep 5

            echo "=== 检查容器状态 ==="
            ssh $SSH_OPTS "$DEPLOY_TARGET" /bin/sh <<'REMOTE_SCRIPT'
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
              fix_ssh_key_permissions() {
                chmod 600 "$SSH_KEY" 2>/dev/null || true

                if command -v powershell.exe >/dev/null 2>&1; then
                  SSH_KEY_PATH="$SSH_KEY" powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command '
$path = $env:SSH_KEY_PATH
$acl = Get-Acl -LiteralPath $path
$acl.SetAccessRuleProtection($true, $false)
foreach ($rule in @($acl.Access)) {
  [void]$acl.RemoveAccessRuleAll($rule)
}
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($current, "FullControl", "Allow")
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $path -AclObject $acl
' >/dev/null 2>&1 || true
                fi

                if command -v cmd.exe >/dev/null 2>&1; then
                  CURRENT_USER="$(whoami 2>/dev/null || printf '%s' "${USERNAME:-}")"
                  cmd.exe /c icacls "$SSH_KEY" /inheritance:r >/dev/null 2>&1 || true
                  cmd.exe /c icacls "$SSH_KEY" /remove:g "*S-1-5-11" "*S-1-5-32-545" "*S-1-1-0" "NT AUTHORITY\\Authenticated Users" "BUILTIN\\Users" "Everyone" >/dev/null 2>&1 || true
                  if [ -n "$CURRENT_USER" ]; then
                    cmd.exe /c icacls "$SSH_KEY" /grant:r "$CURRENT_USER:F" >/dev/null 2>&1 || true
                  fi
                fi
              }
              fix_ssh_key_permissions
              DEPLOY_TARGET="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
              SSH_OPTS="-i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p ${DEPLOY_SSH_PORT}"
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
