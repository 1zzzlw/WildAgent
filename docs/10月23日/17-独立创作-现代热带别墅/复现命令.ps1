$ErrorActionPreference = 'Stop'
$caseDirectory = $PSScriptRoot
$projectDirectory = (Resolve-Path (Join-Path $caseDirectory '../../..')).Path
$env:PYTHONIOENCODING = 'utf-8'
$env:SystemRoot = [Environment]::GetFolderPath('Windows')
$env:WINDIR = $env:SystemRoot
$wildFile = Join-Path $caseDirectory '棕影水院-现代热带别墅.wild'

# 从已保存的DesignDocument重放；无需重新创建设计，也不读取skill。
Push-Location $projectDirectory
try {
    python -X utf8 (Join-Path $caseDirectory '02-生成/展开本方案.py')
    if ($LASTEXITCODE -ne 0) { throw '展开失败' }
    python -X utf8 (Join-Path $caseDirectory '03-验证/检查与剖切.py')
    if ($LASTEXITCODE -ne 0) { throw 'Schema或空间检查失败' }
    node wild-web/scripts/validate-generated.mjs $wildFile
    if ($LASTEXITCODE -ne 0) { throw 'Core重建失败' }
    foreach ($scene in @(@('day','日景'), @('night','夜景'))) {
        node wild-web/scripts/render-baseline.mjs $wildFile (Join-Path $caseDirectory "04-效果图/$($scene[1])") --presentation --quality=high "--time=$($scene[0])"
        if ($LASTEXITCODE -ne 0) { throw "渲染失败: $($scene[0])" }
    }
    node wild-web/scripts/render-baseline.mjs (Join-Path $caseDirectory '05-剖切/室内剖切.wild') (Join-Path $caseDirectory '05-剖切/效果图') --presentation --quality=high --time=day
    if ($LASTEXITCODE -ne 0) { throw '剖切渲染失败' }
} finally {
    Pop-Location
}
# 浏览器默认路径沿用当前项目；不同机器请设置CHROMIUM_PATH或向渲染脚本传第三个路径参数。
