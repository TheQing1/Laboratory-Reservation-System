# ============================================================
# 智能实验室预约系统 —— 一键启动前后端（Windows PowerShell）
#
#   用法：  pwsh -File scripts/start-all.ps1
#
# 后端: http://127.0.0.1:8000  (API 文档 /docs)
# 前端: http://127.0.0.1:5173
# 按 Ctrl+C 可同时停止两个服务。
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "=== 智能实验室预约系统 ===" -ForegroundColor Cyan

# ---- 检查依赖 ----
if (-not (Test-Path "$root\backend\app\main.py")) {
    Write-Host "× 未找到后端代码，请确认脚本位于 scripts/ 目录下" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "$root\frontend\node_modules")) {
    Write-Host "! 前端依赖未安装，正在执行 npm install ..." -ForegroundColor Yellow
    Push-Location "$root\frontend"
    npm install --ignore-scripts
    Pop-Location
}

# ---- 启动后端 ----
Write-Host "`n[1/2] 启动后端 http://127.0.0.1:8000 ..." -ForegroundColor Green
$backend = Start-Process -PassThru -NoNewWindow -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory "$root\backend"

Start-Sleep -Seconds 4

# ---- 启动前端 ----
Write-Host "[2/2] 启动前端 http://127.0.0.1:5173 ..." -ForegroundColor Green
$frontend = Start-Process -PassThru -NoNewWindow -FilePath "node" `
    -ArgumentList "scripts/dev-no-esbuild.mjs" `
    -WorkingDirectory "$root\frontend"

Write-Host @"

============================================================
  系统已启动
    前端页面 : http://127.0.0.1:5173
    API 文档 : http://127.0.0.1:8000/docs
    演示账号 : admin / admin123   （管理员）
               student / student123 （学生）
  按 Ctrl+C 停止全部服务
============================================================
"@ -ForegroundColor Cyan

try {
    Wait-Process -Id $backend.Id, $frontend.Id
} finally {
    Write-Host "`n正在停止服务 ..." -ForegroundColor Yellow
    foreach ($p in @($backend, $frontend)) {
        if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
    Write-Host "已停止。" -ForegroundColor Green
}
