param([ValidateRange(1024, 65535)][int]$Port = 5173)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot 'frontend'
if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot 'node_modules/vite'))) {
    throw 'Install the frontend dependencies first: cd frontend; npm ci. See frontend/README.md.'
}
Push-Location -LiteralPath $FrontendRoot
try {
    & npm run dev -- --port $Port
    if ($LASTEXITCODE -ne 0) { throw "Frontend exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
