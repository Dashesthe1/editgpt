# editgpt

EditGPT is a new project for building GPT into a professional After Effects editor by giving it human-like senses and control while retaining machine-precision tools.

## Current milestone: Eyes + Hands observe-act-verify bridge

Eyes remains the first and highest-priority perception subsystem. The goal is not "periodic screenshots"; it is a complete visual service that lets GPT request reliable evidence about live After Effects playback and exact source footage.

Hands is now being added as a separate write-capable subsystem so GPT can execute mouse and keyboard actions without weakening the read-only Eyes boundary.

The target stack is intentionally capability-first and local/no-recurring-inference-cost where practical:

- **DXcam** — low-latency Windows/After Effects capture.
- **Qwen3-VL** — semantic image/video understanding.
- **SAM 3.1** — promptable object detection, segmentation, and multi-object video tracking.
- **TAPNext++** — arbitrary point tracking and re-detection.
- **NVIDIA Optical Flow SDK** — high-rate motion vectors when supported.
- **OpenCV** — portable motion/image measurements and fallback algorithms.
- **PyNvVideoCodec** — GPU source-footage decode on NVIDIA hardware.
- **FFmpeg/PyAV** — exact-source compatibility/fallback decode.
- **TransNetV2 / PySceneDetect** — shot-boundary detection.
- **Native Win32 SendInput** — local deterministic mouse/keyboard execution for Hands.

The codebase exposes these systems through stable Eyes and Hands APIs so GPT never needs to know which backend produced an observation or executed an action.

## Proven live-capture baseline

The Windows + After Effects capture layer is proven.

Initial proof:

- target rate: **60 fps**
- newly presented frames observed: **55.59 fps**
- target-rate ratio: **92.65%**
- screen activity: **active**
- diagnostic: **capture_rate_healthy**

Follow-up two-mode diagnostic:

- truthful consumer rate: **56.68 fps**
- truthful unique-present rate: **57.00 fps**
- paced consumer rate: **59.38 fps**
- paced unique-present rate: **58.42 fps**
- interpretation: **capture_pipeline_and_unique_present_rate_healthy**

Saved frames from both phases visibly followed different moments of the actual After Effects preview. The earlier ~40 fps MCP run therefore was not a structural capture ceiling.

DXcam remains in `video_mode=False` for production Eyes so EditGPT preserves truthful newly presented-frame timing. `video_mode=True` is diagnostic only.

## Proven local Eyes MCP

The dedicated local EditGPT Eyes MCP is working end-to-end. The development server binds to loopback by default and exposes:

- `eyes_start_live`
- `eyes_status`
- `eyes_stop_live`
- `eyes_latest_frame`
- `eyes_recent_frames`
- `eyes_frame`
- `eyes_motion_between`

A local MCP client successfully discovered all seven tools, started capture, read status, retrieved a real JPEG frame, and stopped capture. The MCP uses the official MCP Python SDK v2. Do not expose this development server publicly without adding the protected transport/authentication layer first.

## Hands v1

Hands is intentionally a second MCP security boundary because it can modify the desktop. Its local endpoint is `http://127.0.0.1:8766/mcp`.

Current Hands contract:

- starts **disarmed**;
- defaults to `AfterFX.exe` only;
- verifies the foreground process before every mouse/keyboard action;
- can focus an allowlisted After Effects window;
- supports move, click/double-click, scroll, keypress, Unicode text, drag, and wait;
- accepts a compact computer-use-style action object so hosted or local controllers can share the same execution surface;
- keeps screenshots and visual reasoning in Eyes.

The live Hands proof is non-destructive. The paired controller bridge now also normalizes DPI to physical pixels, exposes Eyes encoded/capture geometry, safely maps model-visible coordinates to screen coordinates, fails closed when multi-monitor geometry is ambiguous, and can use local Qwen3-VL to choose a visible UI target before Hands moves to it.

## Semantic Eyes stage

The next perception capability under test is local semantic sight.

Detected workstation hardware:

- NVIDIA RTX A4500
- approximately 20 GB VRAM

For the live semantic eye, the current target is **Qwen3-VL-8B-Instruct Q8_0** through `llama.cpp`. This is intentionally higher fidelity than Q4 while still leaving practical GPU headroom for After Effects, the vision projector, context/KV cache, and later Eyes services. The 30B Q4 model remains a candidate for a slower deep-inspection mode rather than the default live model.

## One-command automation

The normal Windows entry point is now:

```powershell
cd $HOME\editgpt
.\editgpt.ps1
```

That single launcher now:

1. checks GitHub and fast-forwards the repo when the working tree is clean;
2. never overwrites local changes automatically;
3. bootstraps dependencies and runs tests when the checked-out revision changes;
4. installs/locates llama.cpp when semantic sight needs it;
5. starts the local Eyes MCP if it is not already listening;
6. starts the local Hands MCP if it is not already listening;
7. starts the Qwen semantic server if it is not already ready;
8. keeps the managed services in the background with persistent logs;
9. preserves/reuses the current After Effects process rather than restarting it.

The first Qwen launch may continue in the background while the official model and vision projector download/load. Check status with:

```powershell
.\editgpt.ps1 -Action status
```

Run the current proofs with:

```powershell
.\editgpt.ps1 -Action proof-capture
.\editgpt.ps1 -Action proof-mcp
.\editgpt.ps1 -Action proof-hands
.\editgpt.ps1 -Action proof-loop
.\editgpt.ps1 -Action proof-semantic-pointer
.\editgpt.ps1 -Action proof-semantic
```

Other useful commands:

```powershell
.\editgpt.ps1 -Action doctor
.\editgpt.ps1 -Action logs -Service eyes_mcp
.\editgpt.ps1 -Action logs -Service hands_mcp
.\editgpt.ps1 -Action logs -Service semantic_qwen
.\editgpt.ps1 -Action down
```

See `docs/ORCHESTRATOR.md` for lifecycle and safety behavior.

## Local state

The orchestrator keeps its machine-specific state under `.editgpt/`, which is ignored by Git. Proof evidence remains under `artifacts/`.

Current local endpoints:

- Eyes MCP: `http://127.0.0.1:8765/mcp`
- Hands MCP: `http://127.0.0.1:8766/mcp`
- Qwen semantic server: `http://127.0.0.1:8080/v1`

These are local development endpoints only. A protected ChatGPT-facing route is a separate future architecture checkpoint.

## Design rule

Use the strongest zero-recurring-cost tool that the available hardware can run reliably. Step down only for a real blocker such as hardware support, Windows compatibility, unacceptable latency, or integration failure.
