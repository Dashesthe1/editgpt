$ErrorActionPreference = "Stop"

Write-Host "EditGPT Eyes semantic setup"
Write-Host "Target live semantic model: Qwen3-VL-8B-Instruct Q8_0"
Write-Host "Inference runtime: llama.cpp on localhost only"
Write-Host ""

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget was not found. Install/update App Installer from Microsoft, then rerun this script."
}

$Llama = Get-Command llama -ErrorAction SilentlyContinue
if (-not $Llama) {
    Write-Host "llama.cpp is not installed. Installing the official WinGet package..."
    & winget install --id ggml.llamacpp -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "llama.cpp installation failed with exit code $LASTEXITCODE"
    }
    $Llama = Get-Command llama -ErrorAction SilentlyContinue
}

if (-not $Llama) {
    Write-Host "llama.cpp was installed, but this PowerShell session does not see the new PATH entry yet."
    Write-Host "Close PowerShell, open a new PowerShell window, return to $PWD, and rerun this script."
    exit 0
}

Write-Host ""
Write-Host "llama.cpp detected: $($Llama.Source)"
& llama --version
if ($LASTEXITCODE -ne 0) {
    throw "llama.cpp is installed but failed its version check."
}

Write-Host ""
Write-Host "Semantic runtime setup is ready."
Write-Host ""
Write-Host "In PowerShell window 1, start the local Qwen server with:"
Write-Host "llama serve -hf Qwen/Qwen3-VL-8B-Instruct-GGUF:Q8_0 --host 127.0.0.1 --port 8080 -ngl 99 -c 8192"
Write-Host ""
Write-Host "The first launch downloads roughly 9.5 GB of official Qwen model + vision-projector files."
Write-Host "Leave that server running. Then in PowerShell window 2 run:"
Write-Host ".\.venv\Scripts\python.exe .\scripts\prove_semantic.py"
