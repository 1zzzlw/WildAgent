# HTTPS/SSL 配置指南

为 `www.zzzlew.asia` 添加 Let's Encrypt 免费 SSL 证书。

**环境**：阿里云 ECS `39.106.183.13`，Ubuntu 22.04，Docker 部署。

---

## 架构

```
宿主机证书目录:
/opt/wild-agent/certbot/
├── letsencrypt/live/www.zzzlew.asia/
│   ├── fullchain.pem
│   └── privkey.pem
└── www/                  # ACME webroot（预留，暂未使用）

请求流程:
浏览器 :443 → wild-web(nginx) ─→ /api/*, /ws/* → wild-server:8000
                               ─→ 其他 → 静态文件
浏览器 :80  → /.well-known/acme-challenge/ → 本地文件
           → 其他 → 301 → https://...
```

---

## 一、申请证书（服务器上操作，先做这一步）

**顺序**：先拿证书，再部署代码。新版 nginx.conf 引用了证书路径，如果证书不存在容器会启动失败。

### 1.1 创建目录 + 安装 certbot

```bash
ssh root@39.106.183.13
mkdir -p /opt/wild-agent/certbot/{letsencrypt,www}
sudo apt update && sudo apt install certbot -y
```

### 1.2 申请证书（DNS 验证）

HTTP-01 standalone 模式在阿里云上无法使用（详见踩坑记录），最终采用 DNS 验证。

```bash
sudo certbot certonly --manual \
  --preferred-challenges dns \
  -d www.zzzlew.asia \
  --email 1400377637@qq.com \
  --agree-tos \
  --config-dir /opt/wild-agent/certbot/letsencrypt \
  --work-dir /opt/wild-agent/certbot/www
```

执行后会输出一条 TXT 记录。去**阿里云 DNS 控制台**添加：

| 主机记录 | 类型 | 值 |
|----------|------|-----|
| `_acme-challenge.www` | TXT | certbot 输出的随机字符串 |

验证 DNS 已生效：

```bash
dig _acme-challenge.www.zzzlew.asia TXT
```

确认能看到记录值后，回到终端按回车。成功输出：

```
Certificate is saved at: /opt/wild-agent/certbot/letsencrypt/live/www.zzzlew.asia/fullchain.pem
Expires on 2026-11-10
```

### 1.3 确认证书

```bash
ls /opt/wild-agent/certbot/letsencrypt/live/www.zzzlew.asia/
# fullchain.pem  privkey.pem  cert.pem  chain.pem  README
```

---

## 二、修改项目文件

### 2.1 `wild-web/nginx.conf`

```nginx
server {
    listen 80;
    server_name www.zzzlew.asia;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name www.zzzlew.asia;

    ssl_certificate /etc/letsencrypt/live/www.zzzlew.asia/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.zzzlew.asia/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    add_header Strict-Transport-Security "max-age=63072000" always;

    root /usr/share/nginx/html;
    index index.html;
    client_max_body_size 20m;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /ws/ {
        proxy_pass http://wild-server:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    location /api/ {
        proxy_pass http://wild-server:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 2.2 `wild-web/Dockerfile`

在 `EXPOSE 80` 下面加：

```dockerfile
EXPOSE 443
```

### 2.3 `Jenkinsfile` — 两处修改

**a) `start_web()` 函数**：添加 443 端口映射 + 证书卷挂载

```bash
start_web() {
  web_image="$1"
  docker run -d \
    --name wild-web \
    --restart unless-stopped \
    --network wild-net \
    -p 80:80 \
    -p 443:443 \
    -v /opt/wild-agent/certbot/letsencrypt:/etc/letsencrypt:ro \
    -v /opt/wild-agent/certbot/www:/var/www/certbot:ro \
    "$web_image"
}
```

**b) web 就绪检查**：原 `wget` 方式收到 HTTP 301 会退出非 0，改用 `docker top` 检查 nginx 进程

```bash
# 旧（第 365 行）：
if docker exec wild-web wget -q -O /dev/null http://127.0.0.1/ >/dev/null 2>&1; then

# 新：
if docker top wild-web 2>/dev/null | grep -q nginx; then
```

### 2.4 提交

```bash
git add wild-web/nginx.conf wild-web/Dockerfile Jenkinsfile
git commit -m "添加 HTTPS 支持"
git push
```

---

## 三、部署后验证

```bash
# nginx 配置语法
docker exec wild-web nginx -t

# HTTP → 301
curl -I http://www.zzzlew.asia

# HTTPS → 200
curl -I https://www.zzzlew.asia

# API 代理
curl https://www.zzzlew.asia/api/health/ready

# 端口
docker port wild-web
```

---

## 四、证书续期

证书到期日 **2026-11-10**。本次使用 `--manual` DNS 验证，**不会自动续期**。到期前需要手动操作：

```bash
# 到期前 30 天内，在服务器上执行：
sudo certbot renew \
  --config-dir /opt/wild-agent/certbot/letsencrypt \
  --work-dir /opt/wild-agent/certbot/www

# 续期成功后 reload nginx
docker exec wild-web nginx -s reload
```

---

## 五、踩坑记录

| # | 问题 | 现象 | 根因 | 解决 |
|---|------|------|------|------|
| 1 | Docker certbot standalone | 403 | Docker iptables + 阿里云 WAF 拦截外部 HTTP 请求 | 改 DNS 验证 |
| 2 | `--network host` 也 403 | 403 | 确认非 Docker 问题，阿里云安全产品拦截 | 同上 |
| 3 | 宿主机原生 certbot 也 403 | 403 | 同上，80 端口空闲但中间层拦截 | 同上 |
| 4 | HTTPS 部署后 Jenkins 回滚 | web 就绪检查超时 | `wget` 收到 HTTP 301 返回码，视为失败退出非 0 | 换 `docker top` 检查 nginx 进程 |
| 5 | `--manual` 不自动续期 | 需手动续期 | DNS manual 模式设计如此 | 到期前手动 renew |

### 核心教训

- **阿里云 ECS 用 DNS-01 验证**，HTTP-01 容易被 WAF/防火墙拦截
- **先拿证书再部署代码**，避免新版 nginx 因缺证书启动失败（实际就是按这个顺序做的，没问题）
- **wget 不认 301**，HTTPS 上线后 Jenkins 就绪检查需要改成不依赖 HTTP 响应码的方式
