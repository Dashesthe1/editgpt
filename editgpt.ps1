param(
    [ValidateSet("up", "status", "down", "doctor", "proof-capture", "proof-mcp", "proof-hands", "proof-loop", "proof-semantic-pointer", "proof-semantic-click", "proof-hands-ui", "proof-controller", "proof-drag", "proof-semantic", "logs")]
    [string]$Action = "up",
    [ValidateSet("eyes_mcp", "hands_mcp", "semantic_qwen")]
    [string]$Service = "eyes_mcp",
    [switch]$NoUpdate,
    [switch]$ForceBootstrap,
    [switch]$NoSemantic
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

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

function Refresh-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Test-LlamaRuntime {
    return [bool]((Get-Command llama-server -ErrorAction SilentlyContinue) -or (Get-Command llama -ErrorAction SilentlyContinue))
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is not available on PATH."
}

Write-Host "EditGPT orchestrator"
Write-Host "Repository: $Root"

if (-not $NoUpdate) {
    $dirty = (& git status --porcelain) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect git working tree."
    }
    if ([string]::IsNullOrWhiteSpace($dirty)) {
        Write-Host "Checking GitHub for a fast-forward update..."
        Invoke-Checked { & git pull --ff-only } "git pull failed."
    } else {
        Write-Warning "Working tree has local changes; automatic git pull was skipped so EditGPT does not overwrite them."
        Write-Host $dirty
    }
}

$RuntimeDir = Join-Path $Root ".editgpt"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$StampPath = Join-Path $RuntimeDir "bootstrap_commit.txt"
$currentCommit = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read current git revision."
}
$stampedCommit = if (Test-Path $StampPath) { (Get-Content $StampPath -Raw).Trim() } else { "" }
$needsBootstrap = $ForceBootstrap -or (-not (Test-Path $VenvPython)) -or ($stampedCommit -ne $currentCommit)

if ($needsBootstrap) {
    $ExistingControlExe = Join-Path $Root ".venv\Scripts\editgpt-control.exe"
    if (Test-Path $ExistingControlExe) {
        Write-Host "Stopping managed EditGPT services before revision bootstrap..."
        & $ExistingControlExe down | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Unable to stop one or more managed EditGPT services before bootstrap; continuing with validation."
        }
    }
    Write-Host "Bootstrapping/validating this EditGPT revision..."
    Invoke-Checked {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\setup_windows.ps1")
    } "EditGPT bootstrap failed."
    Set-Content -Path $StampPath -Value $currentCommit -Encoding ascii
} else {
    Write-Host "Environment already validated for commit $($currentCommit.Substring(0, 8))."
}

$needsSemantic = (-not $NoSemantic) -and ($Action -in @("up", "proof-semantic", "proof-semantic-pointer", "proof-semantic-click", "proof-hands-ui", "proof-controller", "proof-drag"))
if ($needsSemantic -and -not (Test-LlamaRuntime)) {
    Write-Host "Semantic runtime is missing; installing/locating llama.cpp automatically..."
    Invoke-Checked {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\setup_semantic_windows.ps1")
    } "Semantic runtime setup failed."
    Refresh-ProcessPath
}

$ControlExe = Join-Path $Root ".venv\Scripts\editgpt-control.exe"
if (-not (Test-Path $ControlExe)) {
    throw "editgpt-control entry point is missing after bootstrap: $ControlExe"
}

switch ($Action) {
    "up" {
        if ($NoSemantic) {
            Invoke-Checked { & $ControlExe up --no-semantic } "EditGPT service startup failed."
        } else {
            Invoke-Checked { & $ControlExe up } "EditGPT service startup failed."
        }
    }
    "status" {
        Invoke-Checked { & $ControlExe status } "EditGPT status failed."
    }
    "down" {
        Invoke-Checked { & $ControlExe down } "EditGPT shutdown failed."
    }
    "doctor" {
        Invoke-Checked { & $ControlExe doctor } "EditGPT doctor failed."
    }
    "proof-capture" {
        Invoke-Checked { & $ControlExe proof capture } "Capture proof failed."
    }
    "proof-mcp" {
        Invoke-Checked { & $ControlExe proof mcp } "Eyes MCP proof failed."
    }
    "proof-hands" {
        Invoke-Checked { & $ControlExe proof hands } "Hands MCP proof failed."
    }
    "proof-loop" {
        Invoke-Checked { & $ControlExe proof loop } "Observe-act-verify proof failed."
    }
    "proof-semantic-pointer" {
        Invoke-Checked { & $ControlExe proof semantic-pointer } "Semantic pointer proof failed."
    }
    "proof-semantic-click" {
        Invoke-Checked { & $ControlExe proof semantic-click } "Semantic click proof failed."
    }
    "proof-hands-ui" {
        Invoke-Checked { & $ControlExe proof hands-ui } "Hands UI interaction proof failed."
    }
    "proof-controller" {
        Invoke-Checked { & $ControlExe proof controller } "Closed-loop controller proof failed."
    }
    "proof-drag" {
        Invoke-Checked { & $ControlExe proof drag } "Drag proof failed."
    }
    "proof-semantic" {
        Invoke-Checked { & $ControlExe proof semantic } "Semantic proof failed."
    }
    "logs" {
        Invoke-Checked { & $ControlExe logs $Service } "Unable to read EditGPT service log."
    }
}
