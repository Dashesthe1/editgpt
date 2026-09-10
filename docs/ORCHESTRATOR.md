# EditGPT Local Orchestrator

The orchestrator removes repetitive terminal work while keeping local machine control explicit and recoverable.

## Goals

- one normal entry point: `./editgpt.ps1`
- fast-forward the repository when the working tree is clean
- never overwrite local changes automatically
- bootstrap/test only when the checked-out revision changes (or when forced)
- install/locate the local llama.cpp semantic runtime when needed
- keep EditGPT Eyes MCP, Hands MCP, and Qwen services running in the background
- write service logs under `.editgpt/logs/`
- expose status, proofs, diagnostics, and artifacts from one control CLI
- reuse the current After Effects process; never close/restart AE by default

## Commands

From the repository root on Windows:

```powershell
# Default: update, validate, install missing semantic runtime, start services
.\editgpt.ps1

# Same explicitly
.\editgpt.ps1 -Action up

# Inspect repo/AE/services/artifacts
.\editgpt.ps1 -Action status

# Run health/tests/environment checks
.\editgpt.ps1 -Action doctor

# Run one proof
.\editgpt.ps1 -Action proof-capture
.\editgpt.ps1 -Action proof-mcp
.\editgpt.ps1 -Action proof-hands
.\editgpt.ps1 -Action proof-semantic

# Read service logs
.\editgpt.ps1 -Action logs -Service eyes_mcp
.\editgpt.ps1 -Action logs -Service hands_mcp
.\editgpt.ps1 -Action logs -Service semantic_qwen

# Stop only services previously started by the orchestrator
.\editgpt.ps1 -Action down
```

Useful switches:

- `-NoUpdate`: skip the GitHub fast-forward check.
- `-ForceBootstrap`: rerun dependency installation/tests even when the revision stamp matches.
- `-NoSemantic`: start the Eyes and Hands MCP services without the semantic model.

## Service model

The Python control plane is `editgpt-control` / `editgpt.orchestrator`.

Current managed services:

1. `eyes_mcp`
   - read-only visual evidence service
   - loopback endpoint: `http://127.0.0.1:8765/mcp`
   - started with the current Python environment
   - log: `.editgpt/logs/eyes_mcp.log`

2. `hands_mcp`
   - write-capable guarded mouse/keyboard service
   - loopback endpoint: `http://127.0.0.1:8766/mcp`
   - starts disarmed; default target allowlist is `AfterFX.exe`
   - every input action checks the current foreground process
   - log: `.editgpt/logs/hands_mcp.log`

3. `semantic_qwen`
   - loopback OpenAI-compatible endpoint: `http://127.0.0.1:8080/v1`
   - current live model: `Qwen/Qwen3-VL-8B-Instruct-GGUF:Q8_0`
   - prefers `llama-server`; supports the `llama serve` wrapper when that is the installed command
   - requests all practical GPU layers while reserving a 4096 MiB fit margin for AE and other Eyes services
   - log: `.editgpt/logs/semantic_qwen.log`

The first Qwen start may remain in `starting` state while llama.cpp downloads and loads the model. `proof-semantic` waits for readiness rather than asking the user to repeatedly check the server.

## Local state

Runtime state is kept under `.editgpt/` and ignored by Git:

- `bootstrap_commit.txt` - revision that completed bootstrap/tests
- `services.json` - PIDs/commands of processes started by the orchestrator
- `logs/*.log` - persistent service logs

Proof outputs remain under `artifacts/`.

## Safety and lifecycle rules

- Git auto-update uses `git pull --ff-only` only when the working tree is clean.
- A dirty working tree causes update to be skipped, never overwritten.
- The orchestrator does not restart or close After Effects.
- `down` only targets PIDs previously recorded as orchestrator-owned.
- Eyes and Hands are separate MCP security boundaries; adding desktop input does not grant writes to the Eyes service.
- Hands starts disarmed and defaults to `AfterFX.exe` only.
- The MCP and Qwen endpoints remain loopback-only at this stage.
- A protected external ChatGPT-facing route is a separate future checkpoint; do not expose these development listeners directly to the internet.

## Next automation checkpoint

After Hands passes its live Windows proof, connect the controller to the paired Eyes + Hands contracts so one loop can observe the actual AE state, choose an action, execute it, and immediately verify the result. Keep the local services provider-independent so native ChatGPT/Codex computer use or a hosted Responses API computer-use model can be swapped in without redesigning the desktop layer.
