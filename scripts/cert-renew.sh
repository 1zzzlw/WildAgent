#!/bin/bash
#
# Let's Encrypt 证书自动续期脚本
# 放在服务器 crontab 中定期执行，例如每天凌晨 3:17：
#   17 3 * * * /bin/bash /opt/wild-agent/scripts/cert-renew.sh >> /var/log/cert-renew.log 2>&1
#

set -eu

# ========== 配置项 ==========
CERTS_DIR="/opt/wild-agent/certbot/letsencrypt/live"
WEBROOT_DIR="/opt/wild-agent/certbot/www"
CONFIG_DIR="/opt/wild-agent/certbot/letsencrypt"
WORK_DIR="/opt/wild-agent/certbot/www"
WEB_CONTAINER="wild-web"

EMAIL="1400377637@qq.com"
DAYS_BEFORE_EXPIRY=30     # 过期前 30 天触发续期

# ========== 遍历证书 ==========
for cert_dir in "$CERTS_DIR"/*; do
    [ -d "$cert_dir" ] || continue

    domain=$(basename "$cert_dir")
    [ "$domain" = "README" ] && continue

    cert_file="$cert_dir/fullchain.pem"
    [ -f "$cert_file" ] || { echo "[WARN] 未找到证书文件: $cert_file"; continue; }

    echo "========== 检查证书: $domain =========="

    # 获取过期时间戳
    expiration_date=$(openssl x509 -enddate -noout -in "$cert_file" | cut -d= -f2-)
    expiration_ts=$(date -d "$expiration_date" +%s)
    current_ts=$(date +%s)
    days_left=$(( (expiration_ts - current_ts) / 86400 ))

    echo "过期日期: $expiration_date"
    echo "剩余天数: $days_left"

    if [ "$days_left" -gt "$DAYS_BEFORE_EXPIRY" ]; then
        echo "证书仍然有效，跳过续期。"
        echo "--------------------------"
        continue
    fi

    echo "证书将在 $days_left 天后过期，开始续期..."

    # ========== 续期（webroot 模式，不需要停 wild-web） ==========
    #
    # 注意：webroot 模式依赖 nginx 正确处理 /.well-known/acme-challenge/ 路径。
    # 如果阿里云 WAF 仍然拦截外部 HTTP 请求导致 webroot 模式也失败，
    # 则需要临时改用 DNS 手动验证（参考 docs/HTTPS_SETUP.md）。
    #

    if certbot renew \
        --cert-name "$domain" \
        --config-dir "$CONFIG_DIR" \
        --work-dir "$WORK_DIR" \
        --webroot -w "$WEBROOT_DIR" \
        --quiet; then

        echo "证书续期成功，reload nginx..."
        docker exec "$WEB_CONTAINER" nginx -s reload
        echo "续期完成。"
    else
        echo "[ERROR] 证书续期失败，webroot 模式可能被防火墙拦截。"
        echo "请在到期前手动用 DNS 验证续期，参考 docs/HTTPS_SETUP.md。"
    fi

    echo "--------------------------"
done

echo "===== 续期检查完毕 ====="
