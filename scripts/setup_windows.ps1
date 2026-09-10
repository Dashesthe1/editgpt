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

Write-Host "EditGPT v0.1 Windows bootstrap"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.12 first."
}

Invoke-Checked { py -3.12 -c "import sys; print(sys.version)" } "Python 3.12 is required for the current EditGPT toolchain."

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
Write-Host "Normal service launcher:"
Write-Host ".\editgpt.ps1"
Write-Host ""
Write-Host "Live proof commands:"
Write-Host ".\editgpt.ps1 -Action proof-capture"
Write-Host ".\editgpt.ps1 -Action proof-mcp"
Write-Host ".\editgpt.ps1 -Action proof-hands"
Write-Host ".\editgpt.ps1 -Action proof-loop"
Write-Host ".\editgpt.ps1 -Action proof-semantic-pointer"
Write-Host ".\editgpt.ps1 -Action proof-semantic-click"
Write-Host ".\editgpt.ps1 -Action proof-hands-ui"
Write-Host ".\editgpt.ps1 -Action proof-semantic"
