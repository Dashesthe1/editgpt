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

## First runnable proof

The first proof deliberately starts smaller than the final stack:

1. Capture newly presented Windows frames with DXcam.
2. Timestamp and retain them in an exact bounded frame buffer.
3. Keep the hot capture path lightweight so analysis does not starve ingestion.
4. Compute only a tiny downsampled activity probe during capture.
5. Save one visual sample per second after capture completes.
6. Expose structured observations through `EyesService`.
7. Validate timing, buffer correctness, and backend substitution with tests.

Then the high-capability semantic/tracking backends are plugged into the same API one at a time and tested against real footage.

## Development

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[capture,dev]"
pytest
python scripts/check_env.py
```

## First live After Effects proof

Open After Effects with moving footage ready in the Composition viewer. From PowerShell run:

```powershell
.\.venv\Scripts\editgpt-eyes.exe capture --seconds 5 --fps 60
```

The command waits five seconds before capture begins. During that delay, switch to After Effects and start the Composition preview. Keep After Effects visible for the five-second capture window.

Evidence is written to `artifacts/eyes-live-proof/` as a JSON summary plus one JPEG sample per second. The summary distinguishes the target rate, newly presented frame rate, screen activity, and likely failure mode.

DXcam is intentionally used with `video_mode=False` in this proof. That means it reports newly rendered/presented frames rather than fabricating duplicate frames simply to satisfy the requested cadence.

## Design rule

Use the strongest zero-recurring-cost tool that the available hardware can run reliably. Step down only for a real blocker such as hardware support, Windows compatibility, unacceptable latency, or integration failure.
