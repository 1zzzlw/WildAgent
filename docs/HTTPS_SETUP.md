# HTTPS/SSL 配置指南

为 `www.zzzlew.asia` 添加 Let's Encrypt 免费 SSL 证书，实现 HTTPS 访问。

## 架构概览

```
宿主机目录:
/opt/wild-agent/certbot/
├── letsencrypt/          # 证书存储（certbot 管理）
│   └── live/www.zzzlew.asia/
│       ├── fullchain.pem
│       └── privkey.pem
└── www/                  # ACME webroot 共享目录（续期用）

请求流程:
:443 → wild-web(nginx) → /api/*,/ws/* → wild-server:8000
                        → 其他 → 静态文件
:80  → /.well-known/acme-challenge/ → 本地文件（续期验证）
     → 其他 → 301 重定向到 HTTPS
```

## 一、修改项目文件（3 个文件）

### 1. `wild-web/nginx.conf` → 替换为下面的内容

```nginx
# HTTP：仅保留 ACME challenge 路径供 certbot 续期，其余全部跳转 HTTPS
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

# HTTPS：承载全部业务
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

### 2. `wild-web/Dockerfile` → 修改两处

**a) 在 `EXPOSE 80` 下面加一行：**

```dockerfile
EXPOSE 443
```

**b) 完整修改后的 Dockerfile：**

```dockerfile
ARG NODE_BASE_IMAGE=node:22-alpine
ARG NGINX_BASE_IMAGE=nginx:alpine

FROM ${NODE_BASE_IMAGE} AS builder
ARG NPM_REGISTRY=https://registry.npmmirror.com

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --registry=${NPM_REGISTRY}

COPY . .
RUN npm run build

FROM ${NGINX_BASE_IMAGE}

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
EXPOSE 443
```

### 3. `Jenkinsfile` → 修改 `start_web()` 函数

找到 `start_web()` 函数（约第 290 行），当前的代码：

```bash
start_web() {
  web_image="$1"
  docker run -d \
    --name wild-web \
    --restart unless-stopped \
    --network wild-net \
    -p 80:80 \
    "$web_image"
}
```

改成：

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

---

## 二、服务器一次性初始化

> 在服务器 `39.106.183.13` 上执行，只需做一次。
> **时机**：等 Jenkins 首次部署完新配置之后再做（因为新版 nginx.conf 配置了 443，但证书还不存在，nginx 会启动失败）。

### 操作步骤

```bash
# 1. SSH 登录服务器
ssh root@39.106.183.13

# 2. 创建目录
mkdir -p /opt/wild-agent/certbot/{letsencrypt,www}

# 3. 停止 wild-web（释放 80 端口给 certbot 用）
docker stop wild-web

# 4. 用 certbot 容器申请证书（standalone 模式，临时占用 80 端口）
docker run --rm \
  -v /opt/wild-agent/certbot/letsencrypt:/etc/letsencrypt \
  -v /opt/wild-agent/certbot/www:/var/www/certbot \
  -p 80:80 \
  certbot/certbot certonly --standalone \
  -d www.zzzlew.asia \
  --email 你的邮箱@example.com \
  --agree-tos \
  --non-interactive

# 5. 验证证书生成成功
ls -la /opt/wild-agent/certbot/letsencrypt/live/www.zzzlew.asia/
# 应该看到: fullchain.pem  privkey.pem  ...

# 6. 启动 wild-web（现在证书已就位，nginx 可以正常监听 443）
docker start wild-web

# 7. 等待几秒后验证
docker exec wild-web nginx -t          # 配置语法检查
curl -I http://www.zzzlew.asia         # 应返回 301
curl -I https://www.zzzlew.asia        # 应返回 200
```

---

## 三、证书自动续期

Let's Encrypt 证书有效期 90 天，需要自动续期。

在服务器上添加 crontab：

```bash
crontab -e
```

添加下面这行（每天凌晨 3:17 检查一次）：

```
17 3 * * * docker run --rm -v /opt/wild-agent/certbot/letsencrypt:/etc/letsencrypt -v /opt/wild-agent/certbot/www:/var/www/certbot certbot/certbot renew --webroot -w /var/www/certbot --quiet && docker exec wild-web nginx -s reload
```

> **原理**：certbot 会在证书到期前 30 天内才真正续期，其余时间 `renew` 是空操作。续期成功后自动 reload nginx 使新证书生效。

验证续期 cron 是否配置正确：

```bash
# 干跑测试（不会真正续期）
docker run --rm \
  -v /opt/wild-agent/certbot/letsencrypt:/etc/letsencrypt \
  -v /opt/wild-agent/certbot/www:/var/www/certbot \
  certbot/certbot renew --webroot -w /var/www/certbot --dry-run
```

---

## 四、验证清单

部署完成后逐项确认：

| # | 检查项 | 命令 | 预期结果 |
|---|--------|------|----------|
| 1 | nginx 配置语法 | `docker exec wild-web nginx -t` | syntax is ok |
| 2 | HTTP 重定向 | `curl -I http://www.zzzlew.asia` | `301 Moved Permanently`，Location 指向 https |
| 3 | HTTPS 可访问 | `curl -I https://www.zzzlew.asia` | `200 OK` |
| 4 | 证书有效 | `curl -I https://www.zzzlew.asia 2>&1 \| grep -i expire` | 证书信息正常 |
| 5 | API 代理正常 | `curl https://www.zzzlew.asia/api/health/ready` | 返回后端健康状态 |
| 6 | 容器端口映射 | `docker port wild-web` | 同时显示 80 和 443 |
| 7 | WebSocket | 浏览器 console 中 WebSocket 连接使用 `wss://` | 连接成功 |

---

## 五、常见问题

### Q: 如果证书还没申请就部署了新版 Jenkins 怎么办？

nginx 启动时会因为找不到 `/etc/letsencrypt/live/www.zzzlew.asia/fullchain.pem` 而失败，容器无法启动。

**解决**：没关系，按「服务器一次性初始化」的步骤操作即可——证书申请完成后 `docker start wild-web`，容器就能正常启动了。

### Q: 如果 443 端口被云服务商防火墙拦截？

阿里云 ECS 默认只开放了常用端口。需要在**阿里云安全组**中放行 443 端口：

1. 登录阿里云控制台 → ECS → 安全组
2. 添加入方向规则：`端口 443/443`，协议 `TCP`，授权对象 `0.0.0.0/0`

### Q: 续期失败怎么办？

certbot 会在证书过期前 30 天开始尝试续期。如果续期失败，你会在 cron 执行时收到邮件（如果配置了 MAILTO）。也可以手动执行：

```bash
# 查看所有证书状态
docker run --rm \
  -v /opt/wild-agent/certbot/letsencrypt:/etc/letsencrypt \
  certbot/certbot certificates

# 手动续期
docker run --rm \
  -v /opt/wild-agent/certbot/letsencrypt:/etc/letsencrypt \
  -v /opt/wild-agent/certbot/www:/var/www/certbot \
  -p 80:80 \
  certbot/certbot renew --webroot -w /var/www/certbot
```
