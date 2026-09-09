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

The first real After Effects proof passed on Windows:

- target rate: **60 fps**
- newly presented frames observed: **55.59 fps**
- target-rate ratio: **92.65%**
- screen activity: **active**
- diagnostic: **capture_rate_healthy**
- six saved visual samples confirmed that the captured image followed the moving After Effects preview rather than a stale desktop frame.

DXcam remains in `video_mode=False` for truthful newly presented-frame timing. The hot capture loop keeps expensive analysis and JPEG work out of ingestion.

## Local Eyes MCP

The live-capture proof unlocked the next architecture milestone: a dedicated EditGPT Eyes MCP. The development server intentionally binds to loopback by default and exposes:

- `eyes_start_live`
- `eyes_status`
- `eyes_stop_live`
- `eyes_latest_frame`
- `eyes_recent_frames`
- `eyes_frame`
- `eyes_motion_between`

The MCP uses the official MCP Python SDK v2 and can return actual JPEG frames as model-visible image content. Do not expose this development server publicly without adding the protected transport/authentication layer first.

## Development / refresh

```powershell
cd $HOME\editgpt
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

The bootstrap creates/updates the virtual environment, installs capture + MCP + test dependencies, runs the tests, and reports NVIDIA GPU model/VRAM so the strongest practical Qwen3-VL configuration can be selected next.

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

The client waits five seconds before starting live capture so you can switch to After Effects and play the Composition preview. It validates the MCP tool list, starts Eyes through MCP, retrieves status, requests a real model-visible JPEG frame, stops Eyes, and writes proof files to `artifacts/eyes-mcp-proof/`.

The local MCP endpoint is `http://127.0.0.1:8765/mcp`. This is a local development proof only; the ChatGPT-facing route will be added after the local server surface is validated.

## Design rule

Use the strongest zero-recurring-cost tool that the available hardware can run reliably. Step down only for a real blocker such as hardware support, Windows compatibility, unacceptable latency, or integration failure.
