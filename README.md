# editgpt

EditGPT is a new project for building GPT into a professional After Effects editor by giving it human-like senses and control while retaining machine-precision tools.

## Current milestone: Eyes v1

Eyes is the first and highest-priority subsystem. The goal is not "periodic screenshots"; it is a complete visual service that lets GPT request reliable evidence about live After Effects playback and exact source footage.

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

The codebase exposes these systems through a stable Eyes API so GPT never needs to know which backend produced an observation.

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

## Semantic Eyes stage

The next capability under test is local semantic sight.

Detected workstation hardware:

- NVIDIA RTX A4500
- approximately 20 GB VRAM

For the live semantic eye, the current target is **Qwen3-VL-8B-Instruct Q8_0** through `llama.cpp`. This is intentionally higher fidelity than Q4 while still leaving practical GPU headroom for After Effects, the vision projector, context/KV cache, and later Eyes services. The 30B Q4 model remains a candidate for a slower deep-inspection mode, but it is too close to the workstation's total VRAM to make it the default live model while AE is active.

Set up the local semantic runtime:

```powershell
cd $HOME\editgpt
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\setup_semantic_windows.ps1
```

Then start Qwen in PowerShell window 1:

```powershell
llama serve -hf Qwen/Qwen3-VL-8B-Instruct-GGUF:Q8_0 --host 127.0.0.1 --port 8080 -ngl 99 -c 8192
```

The first launch downloads the official Qwen GGUF model and vision projector. Leave that server running.

In PowerShell window 2, prove semantic interpretation against the truthful AE frame captured by the prior diagnostic:

```powershell
cd $HOME\editgpt
.\.venv\Scripts\python.exe .\scripts\prove_semantic.py
```

Evidence is written to:

```text
artifacts/semantic-proof/
  source.jpg
  semantic_result.json
```

This stage is not considered passed merely because the model returns text. We inspect whether it accurately identifies the application, visible footage, subjects/objects, composition, readable UI state, editing-relevant details, and uncertainty without inventing temporal information that a single frame cannot support.

## Development / refresh

```powershell
cd $HOME\editgpt
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

The bootstrap creates/updates the virtual environment, installs capture + MCP + test dependencies, runs the tests, and reports NVIDIA GPU model/VRAM.

## Live capture proof

Open After Effects with moving footage ready in the Composition viewer. From PowerShell run:

```powershell
.\.venv\Scripts\editgpt-eyes.exe capture --seconds 5 --fps 60
```

The command waits five seconds before capture begins. During that delay, switch to After Effects and start the Composition preview. Keep After Effects visible for the five-second capture window.

Evidence is written to `artifacts/eyes-live-proof/` as a JSON summary plus one JPEG sample per second.

## Local MCP proof

In PowerShell window 1, start the local server:

```powershell
.\.venv\Scripts\editgpt-eyes-mcp.exe --transport streamable-http --host 127.0.0.1 --port 8765
```

Leave it running. In PowerShell window 2, run:

```powershell
.\.venv\Scripts\python.exe .\scripts\prove_mcp.py
```

The local MCP endpoint is `http://127.0.0.1:8765/mcp`.

## Design rule

Use the strongest zero-recurring-cost tool that the available hardware can run reliably. Step down only for a real blocker such as hardware support, Windows compatibility, unacceptable latency, or integration failure.
