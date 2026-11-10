# 后端检查脚本。
# HBuilder V 没有 CLI，前端编译/运行请在 HBuilder V GUI 中完成；
# -Frontend 只做前端静态检查（manifest / pages.json / 页面文件），不代表已编译。

param(
    [switch]$Frontend
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'dango-backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python venv not found: $python`nCreate it first: cd dango-backend; py -3.15 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}

Push-Location $backend
try {
    Write-Host '== python ==' -ForegroundColor Cyan
    & $python -c "import sys"
    if ($LASTEXITCODE -ne 0) {
        throw 'Python venv is broken. Recreate it: Rename-Item .venv .venv.broken; py -3.15 -m venv .venv; .venv/Scripts/python.exe -m pip install -r requirements.txt'
    }

    Write-Host '== ruff format --check ==' -ForegroundColor Cyan
    & $python -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'ruff format failed; run: python -m ruff format .' }

    Write-Host '== ruff check ==' -ForegroundColor Cyan
    & $python -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'ruff check failed' }

    Write-Host '== pytest ==' -ForegroundColor Cyan
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed' }
}
finally {
    Pop-Location
}

if ($Frontend) {
    $frontendRoot = Join-Path $root 'dango-frontend'
    Write-Host '== frontend static checks ==' -ForegroundColor Cyan

    $manifest = Join-Path $frontendRoot 'manifest.json'
    if (-not (Test-Path -LiteralPath $manifest)) { throw "manifest.json not found: $manifest" }
    if (-not (Select-String -Path $manifest -Pattern '"vapor"\s*:\s*true' -Quiet)) {
        throw "manifest.json does not enable uni-app x vapor mode: $manifest"
    }

    $pagesJson = Join-Path $frontendRoot 'pages.json'
    if (-not (Test-Path -LiteralPath $pagesJson)) { throw "pages.json not found: $pagesJson" }
    $pages = Get-Content -LiteralPath $pagesJson -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($page in $pages.pages) {
        $pageFile = Join-Path $frontendRoot ($page.path + '.uvue')
        if (-not (Test-Path -LiteralPath $pageFile)) { throw "Page file missing: $pageFile" }
    }

    Write-Host 'Frontend static checks passed.' -ForegroundColor Green
    Write-Host 'HBuilder V has no CLI. Open dango-frontend in HBuilder V and run/compile from the GUI.' -ForegroundColor Yellow
}

Write-Host 'All checks passed.' -ForegroundColor Green
