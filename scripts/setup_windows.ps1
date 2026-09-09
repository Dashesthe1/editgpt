$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory=$true)][scriptblock]$Command,
        [Parameter(Mandatory=$true)][string]$FailureMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
}

Write-Host "EditGPT Eyes v0.1 Windows bootstrap"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.12 first."
}

Invoke-Checked { py -3.12 -c "import sys; print(sys.version)" } "Python 3.12 is required for the current Eyes toolchain."

if (-not (Test-Path ".venv")) {
    Invoke-Checked { py -3.12 -m venv .venv } "Failed to create the Python virtual environment."
}

$Python = Join-Path $PWD ".venv\Scripts\python.exe"
Invoke-Checked { & $Python -m pip install --upgrade pip } "pip upgrade failed."
Invoke-Checked { & $Python -m pip install -e ".[capture,mcp,dev]" } "EditGPT dependency installation failed."
Invoke-Checked { & $Python -m pytest } "EditGPT tests failed. Bootstrap stopped before claiming success."
Invoke-Checked { & $Python scripts/check_env.py } "Environment probe failed."

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Live capture proof:"
Write-Host ".\.venv\Scripts\editgpt-eyes.exe capture --seconds 5 --fps 60"
Write-Host ""
Write-Host "Local-only Eyes MCP proof:"
Write-Host ".\.venv\Scripts\editgpt-eyes-mcp.exe --transport streamable-http --host 127.0.0.1 --port 8765"
