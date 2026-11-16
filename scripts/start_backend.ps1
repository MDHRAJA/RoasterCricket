param([ValidateRange(1024, 65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $BackendPython)) {
    throw 'Create the project virtual environment and install requirements-backend.txt first. See docs/backend.md.'
}
Push-Location -LiteralPath $ProjectRoot
try {
    & $BackendPython -m backend --port $Port
    if ($LASTEXITCODE -ne 0) { throw "Backend exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
