#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# 用**真浏览器**给 lantu 查看器出图（真光照 / 真阴影 / 真材质）。
#
# 为什么不用系统 Chrome：本机系统 Chrome 的 headless 会 "Missing headless user
# data directory." 或被转交给"现有会话"（exit 21），起不来。改用 Playwright 缓存
# 里那份 Chromium —— 它走 ANGLE/D3D11，能用上真实 GPU。
#
# 前置：查看器 dev server 已在跑
#   cd wild-web/lantu/viewer && node ../../node_modules/vite/bin/vite.js --port 5180 --strictPort
#
# 用法：
#   bash .workbuddy/diag/shot_lantu_viewer.sh                     # 默认机位全套
#   bash .workbuddy/diag/shot_lantu_viewer.sh "pool front aerial"
#   URL_BASE=http://127.0.0.1:5180 EXP=1.15 bash .workbuddy/diag/shot_lantu_viewer.sh pool
# ─────────────────────────────────────────────────────────────
set -uo pipefail

CAMS="${1:-pool front aerial iso}"
URL_BASE="${URL_BASE:-http://127.0.0.1:5180}"
EXP="${EXP:-1.05}"
W="${W:-1600}"
H="${H:-1000}"
DSF="${DSF:-1.5}"
PREFIX="${PREFIX:-viewer_real}"
PANEL="${PANEL:-0}"
GRID="${GRID:-1}"

OUT="${OUT:-E:/AgentProject/WildAgent/wild-web/lantu/docs/renders}"
CHROME="${CHROME:-C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1148/chrome-win/chrome.exe}"

if [ ! -x "$CHROME" ]; then
  echo "❌ 找不到 Playwright Chromium：$CHROME"
  echo "   可先跑 agent-browser install，或改 CHROME=... 指定其他 Chromium。"
  exit 1
fi

mkdir -p "$OUT"
echo "chromium: $CHROME"
echo "url     : $URL_BASE   exposure=$EXP  ${W}x${H} @${DSF}x"
echo

for CAM in $CAMS; do
  UDD="C:/Users/Administrator/AppData/Local/Temp/cbshot_$CAM"
  PNG="$OUT/${PREFIX}_${CAM}.png"
  rm -rf "$UDD" 2>/dev/null
  mkdir -p "$UDD"
  rm -f "$PNG"

  "$CHROME" \
    --headless=new --no-sandbox --no-first-run --no-proxy-server \
    --disable-dev-shm-usage --hide-scrollbars \
    --user-data-dir="$UDD" \
    --window-size="${W},${H}" --force-device-scale-factor="$DSF" \
    --virtual-time-budget=30000 \
    --screenshot="$PNG" \
    "${URL_BASE}/?cam=${CAM}&exp=${EXP}&panel=${PANEL}&grid=${GRID}" \
    >/dev/null 2>&1

  if [ -s "$PNG" ]; then
    # 小于 20KB 基本就是纯背景 —— 大概率是加载失败或还没渲染就截了
    SIZE=$(stat -c %s "$PNG" 2>/dev/null || echo 0)
    if [ "$SIZE" -lt 20000 ]; then
      echo "⚠️  $CAM  → $(basename "$PNG")  ${SIZE} B  （疑似空图，检查 dev server 与蓝图加载）"
    else
      echo "✅ $CAM  → $(basename "$PNG")  ${SIZE} B"
    fi
  else
    echo "❌ $CAM  → 未生成"
  fi
done
