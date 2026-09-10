$ErrorActionPreference = "Stop"

function Refresh-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Find-LlamaRuntime {
    $server = Get-Command llama-server -ErrorAction SilentlyContinue
    if ($server) {
        return @{ Mode = "llama-server"; Path = $server.Source }
    }
    $meta = Get-Command llama -ErrorAction SilentlyContinue
    if ($meta) {
        return @{ Mode = "llama-serve"; Path = $meta.Source }
    }
    return $null
}

Write-Host "EditGPT Eyes semantic setup"
Write-Host "Target live semantic model: Qwen3-VL-8B-Instruct Q8_0"
Write-Host "Inference runtime: llama.cpp on localhost only"
Write-Host ""

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget was not found. Install/update App Installer from Microsoft, then rerun this script."
}

$Runtime = Find-LlamaRuntime
if (-not $Runtime) {
    Write-Host "llama.cpp is not installed. Installing the official WinGet package..."
    & winget install --id ggml.llamacpp -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "llama.cpp installation failed with exit code $LASTEXITCODE"
    }
    Refresh-ProcessPath
    $Runtime = Find-LlamaRuntime
}

if (-not $Runtime) {
    throw "llama.cpp installed but no llama-server/llama command is visible after refreshing PATH. Open a new PowerShell window and rerun EditGPT."
}

Write-Host ""
Write-Host "llama.cpp detected: $($Runtime.Path)"
& $Runtime.Path --version
if ($LASTEXITCODE -ne 0) {
    throw "llama.cpp is installed but failed its version check."
}

Write-Host ""
Write-Host "Semantic runtime setup is ready for the EditGPT orchestrator."
Write-Host "The orchestrator will start Qwen automatically and keep its log under .editgpt\logs\semantic_qwen.log."
Write-Host "The first Qwen launch will download the official model + vision projector automatically."
