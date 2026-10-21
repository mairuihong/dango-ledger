param(
    [switch]$Frontend
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'dango-backend'

Push-Location $backend
try {
    Write-Host '== ruff format --check ==' -ForegroundColor Cyan
    & .\.venv\Scripts\python.exe -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'ruff format failed; run: python -m ruff format .' }

    Write-Host '== ruff check ==' -ForegroundColor Cyan
    & .\.venv\Scripts\python.exe -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'ruff check failed' }

    Write-Host '== pytest ==' -ForegroundColor Cyan
    & .\.venv\Scripts\python.exe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed' }
}
finally {
    Pop-Location
}

if ($Frontend) {
    $cli = $env:HBUILDERX_CLI
    if (-not $cli) { $cli = 'C:\software\code\HBuilderX\cli.exe' }
    if (-not (Test-Path -LiteralPath $cli)) { throw "HBuilderX CLI not found: $cli" }

    Write-Host '== HBuilderX publish web ==' -ForegroundColor Cyan
    & $cli publish web --project (Join-Path $root 'dango-frontend') --webTitle 'Dango Ledger'
    if ($LASTEXITCODE -ne 0) { throw 'frontend build failed' }
}

Write-Host 'All checks passed.' -ForegroundColor Green
