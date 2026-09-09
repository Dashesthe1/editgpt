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
& $Python -m pip install -e ".[capture,dev]"
& $Python -m pytest
& $Python scripts/check_env.py

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Run the command below, then switch to After Effects during the 5-second delay and start the Composition preview:"
Write-Host ".\.venv\Scripts\editgpt-eyes.exe capture --seconds 5 --fps 60"
