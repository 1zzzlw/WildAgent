# HTTPS/SSL 配置指南

为 `www.zzzlew.asia` 添加 Let's Encrypt 免费 SSL 证书，实现 HTTPS 访问。

**实操环境**：阿里云 ECS `39.106.183.13`，Ubuntu，Docker 部署。

## 架构概览

```
宿主机目录:
/opt/wild-agent/certbot/
├── letsencrypt/          # 证书存储（certbot 管理）
│   └── live/www.zzzlew.asia/
│       ├── fullchain.pem
│       └── privkey.pem
└── www/                  # ACME webroot 共享目录

请求流程:
:443 → wild-web(nginx) → /api/*,/ws/* → wild-server:8000
                        → 其他 → 静态文件
:80  → /.well-known/acme-challenge/ → 本地文件（续期验证）
     → 其他 → 301 重定向到 HTTPS
```

## 正确顺序

```
① 服务器拿证书 → ② 修改代码 → ③ Jenkins 部署
```

**原因**：新版 nginx.conf 引用了证书路径，如果证书不存在容器会启动失败。必须先确保证书在宿主机上就位，再部署新配置。

---

## 一、申请证书（服务器上操作）

### 1.1 创建目录

```bash
ssh root@39.106.183.13
mkdir -p /opt/wild-agent/certbot/{letsencrypt,www}
```

### 1.2 安装 certbot

```bash
sudo apt update
sudo apt install certbot -y
```

### 1.3 申请证书

#### 踩坑记录：为什么 HTTP-01 standalone 验证失败了？

最初尝试了多种方式：

| 方式 | 命令 | 结果 |
|------|------|------|
| Docker 容器 standalone | `docker run ... certbot/certbot certonly --standalone -p 80:80` | ❌ 403 |
| Docker `--network host` | 同上加 `--network host` | ❌ 403 |
| 宿主机原生 certbot | `sudo certbot certonly --standalone` | ❌ 403 |

排查过程：

```bash
# wild-web 已停，80 端口空闲
docker ps | grep wild-web    # 无输出
ss -tlnp | grep :80           # 无监听

# 宿主机没有残留 nginx/apache
systemctl status nginx    # not found
systemctl status apache2  # not found

# iptables 规则无明显拦截
iptables -L -n | head -30
```

**根因**：阿里云的安全产品（WAF/云防火墙）拦截了 Let's Encrypt 验证服务器的 HTTP 请求，返回 403。即使 80 端口空闲、certbot standalone 正常监听，外部验证流量到服务器之前就被中间层挡掉了。加上 Docker 的 iptables NAT 规则也会干扰流量路由，两个因素叠加导致 HTTP-01 验证不可行。

#### 最终方案：DNS 验证

DNS 验证完全绕过 80 端口和网络层问题，只需要在 DNS 控制台添加一条 TXT 记录。

```bash
sudo certbot certonly --manual \
  --preferred-challenges dns \
  -d www.zzzlew.asia \
  --email 1400377637@qq.com \
  --agree-tos \
  --config-dir /opt/wild-agent/certbot/letsencrypt \
  --work-dir /opt/wild-agent/certbot/www
```

执行后会输出类似：

```
Please deploy a DNS TXT record under the name:
_acme-challenge.www.zzzlew.asia
with the following value:
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

去**阿里云 DNS 控制台** → `zzzlew.asia` 的解析记录 → 添加：

| 主机记录 | 类型 | 记录值 |
|----------|------|--------|
| `_acme-challenge.www` | TXT | certbot 输出的随机字符串 |

验证 DNS 生效：

```bash
dig _acme-challenge.www.zzzlew.asia TXT
# 或
nslookup -type=TXT _acme-challenge.www.zzzlew.asia
```

看到返回你添加的记录值后，回到终端按回车。

成功后输出：

```
Successfully received certificate.
Certificate is saved at: /opt/wild-agent/certbot/letsencrypt/live/www.zzzlew.asia/fullchain.pem
Key is saved at:         /opt/wild-agent/certbot/letsencrypt/live/www.zzzlew.asia/privkey.pem
This certificate expires on 2026-11-10.
```

### 1.4 确认证书

```bash
ls /opt/wild-agent/certbot/letsencrypt/live/www.zzzlew.asia/
# fullchain.pem  privkey.pem  cert.pem  chain.pem  README
```

---

## 二、修改项目文件（本地操作）

### 2.1 `wild-web/nginx.conf`

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

### 2.2 `wild-web/Dockerfile`

在 `EXPOSE 80` 下面加一行：

```dockerfile
EXPOSE 443
```

### 2.3 `Jenkinsfile` → `start_web()` 函数

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

### 2.4 提交部署

```bash
git add wild-web/nginx.conf wild-web/Dockerfile Jenkinsfile
git commit -m "添加 HTTPS 支持"
git push
```

---

## 三、部署后验证

```bash
# 1. nginx 配置语法
docker exec wild-web nginx -t

# 2. HTTP 重定向
curl -I http://www.zzzlew.asia
# 预期: 301 Moved Permanently, Location: https://...

# 3. HTTPS 可访问
curl -I https://www.zzzlew.asia
# 预期: 200 OK

# 4. API 代理
curl https://www.zzzlew.asia/api/health/ready

# 5. 容器端口
docker port wild-web
# 应显示 80/tcp 和 443/tcp
```

---

## 四、证书续期

### 4.1 注意事项

本次使用的是 `--manual` DNS 验证，certbot 提示：

> This certificate will not be renewed automatically. Autorenewal of --manual certificates requires the use of an authentication hook script.

**证书到期日：2026-11-10**。到期前 30 天需要手动续期。

### 4.2 续期操作

到期前执行同样的 DNS 验证命令，certbot 会自动复用已有配置：

```bash
sudo certbot renew \
  --config-dir /opt/wild-agent/certbot/letsencrypt \
  --work-dir /opt/wild-agent/certbot/www \
  --dry-run           # 先干跑测试

sudo certbot renew \
  --config-dir /opt/wild-agent/certbot/letsencrypt \
  --work-dir /opt/wild-agent/certbot/www
  # 正式续期，成功后 reload nginx
docker exec wild-web nginx -s reload
```

### 4.3 如果后续阿里云防火墙放行了 80 端口

可以在 nginx HTTPS 部署成功后测试 ACME webroot 是否可达：

```bash
# 从外部测试（不要在服务器上测 localhost）
curl http://www.zzzlew.asia/.well-known/acme-challenge/test
```

返回 404（nginx 返回的）说明路径通畅，就可以用 webroot 模式实现全自动续期：

```bash
# 添加 crontab
sudo crontab -e
# 每天凌晨 3:17：
# 17 3 * * * certbot renew --config-dir /opt/wild-agent/certbot/letsencrypt --work-dir /opt/wild-agent/certbot/www --webroot -w /opt/wild-agent/certbot/www --quiet && docker exec wild-web nginx -s reload
```

---

## 五、踩坑总结

| # | 问题 | 现象 | 根因 | 解决 |
|---|------|------|------|------|
| 1 | Docker standalone 验证失败 | 403 | Docker iptables NAT + 阿里云 WAF 拦截 | 改用 DNS 验证 |
| 2 | `--network host` 也失败 | 403 | 阿里云安全产品仍然拦截 | 同上 |
| 3 | 宿主机原生 certbot 也失败 | 403 | 确认非 Docker 问题，是云防火墙层面 | 同上 |
| 4 | 部署顺序 | 先部署会导致容器 crash | nginx 引用证书路径但证书不存在 | 先拿证书再部署 |
| 5 | `--manual` 不自动续期 | certbot 提示需 manual-auth-hook | DNS manual 模式的设计限制 | 到期前手动续期或改为 webroot 模式 |

### 核心教训

- 阿里云 ECS 上 HTTP-01 验证容易被 WAF/防火墙拦截，**DNS-01 验证最稳**
- **先拿证书再部署**，避免新版 nginx 因缺证书启动失败
- Docker 的 iptables 规则会和云防火墙叠加，排查时要从外到内逐层定位
