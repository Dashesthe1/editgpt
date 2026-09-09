$ErrorActionPreference = "Stop"

Write-Host "EditGPT Eyes v0.1 Windows bootstrap"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.12 first."
}

py -3.12 -c "import sys; print(sys.version)" | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 is required for the current Eyes toolchain."
}

if (-not (Test-Path ".venv")) {
    py -3.12 -m venv .venv
}

$Python = Join-Path $PWD ".venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -e ".[capture,mcp,dev]"
& $Python -m pytest
& $Python scripts/check_env.py

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Live capture proof:"
Write-Host ".\.venv\Scripts\editgpt-eyes.exe capture --seconds 5 --fps 60"
Write-Host ""
Write-Host "Local-only Eyes MCP proof:"
Write-Host ".\.venv\Scripts\editgpt-eyes-mcp.exe --transport streamable-http --host 127.0.0.1 --port 8765"
