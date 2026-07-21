@echo off
chcp 65001 >nul
echo ========================================
echo Wild建筑编辑器 - 开发服务器启动脚本
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] 检查Node.js...
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ 错误：未找到Node.js！
    echo    请先安装Node.js: https://nodejs.org/
    pause
    exit /b 1
)

node --version
npm --version
echo.

echo [2/2] 启动Vite开发服务器...
echo.
echo ✓ 服务器启动后，请在浏览器中访问显示的地址
echo ✓ 通常是: http://localhost:5173/
echo ✓ 然后从菜单加载 lantu\bieshu.wild 文件
echo.
echo ⚠️ 请保持此窗口打开！关闭将停止服务器
echo ========================================
echo.

npm run dev

pause
