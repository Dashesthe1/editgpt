# editgpt

EditGPT is a new project for building GPT into a professional After Effects editor by giving it human-like senses and control while retaining machine-precision tools.

## Current milestone: M5 source + temporal Eyes

Eyes remains the first and highest-priority perception subsystem. The goal is not "periodic screenshots"; it is a complete visual service that lets GPT request reliable evidence about live After Effects playback and exact source footage.

Hands is a separate write-capable subsystem so GPT can execute mouse and keyboard actions without weakening the read-only Eyes boundary. M3 added the closed-loop Controller and Task Policy. M4 adds explicitly scoped, visually verified project mutation with rollback.

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
- **AE Command Surface** — shared registry of native After Effects shortcuts/commands used by every milestone before custom UI automation.

The codebase exposes these systems through stable Eyes, Hands, Controller, and command APIs so GPT does not need to know which backend produced an observation or executed an action.

## Cross-milestone AE command-first architecture

The After Effects Command Surface is a permanent shared capability across **M1, M2, M3, M4, and every future M# phase**.

Before implementing a new EditGPT control tool for an After Effects operation, check in this order:

1. existing registered AE shortcut/command;
2. After Effects Quick Apply;
3. proven After Effects scripting API or `app.executeCommand` route;
4. Eyes + Hands semantic UI navigation;
5. only then build a new custom control primitive if AE does not already expose the needed capability.

This does not replace visual intelligence. Eyes still decides what is visible and verifies outcomes. Hands remains the guarded execution boundary. M3 chooses the best command or UI action. M4 and later editing phases still authorize project mutations and verify/rollback them.

The registry is intentionally broad and expandable. `src/editgpt/controller/ae_commands.py` currently covers more than 140 panel, tool, composition, time, preview, view, footage, effect, layer, property, mask, keyframe, text, and 3D operations. The planner receives only a goal-relevant subset so registry growth does not linearly expand the warm-loop prompt.

See `docs/AE_COMMAND_SURFACE_V1.md` for the milestone integration and expansion contract.

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
- executes registered AE command recipes through the same guarded keyboard boundary;
- keeps screenshots and visual reasoning in Eyes.

Hands v1 is now proven across its full input surface in reversible After Effects UI state. The paired controller bridge normalizes DPI to physical pixels, exposes Eyes encoded/capture geometry, safely maps model-visible coordinates to screen coordinates, fails closed when multi-monitor geometry is ambiguous, and uses local Qwen3-VL to ground visible UI targets. Live proofs now cover semantic move/click, keyboard Esc and Ctrl+A/Backspace, Unicode text entry, mouse-wheel scrolling with visual restoration, and drag/restore of the timeline current-time indicator.

## Controller v1

The first generalized closed-loop controller is implemented locally. It accepts a UI goal, re-observes After Effects, asks local Qwen3-VL for one constrained next action, grounds pointer targets separately, executes through Hands, and visually verifies the expected result before continuing. Pointer actions use a fresh grounding frame plus a target-patch freshness check so inference cannot silently act on materially changed UI evidence.

The planner now prefers registered AE commands before pointer navigation. Because the shared registry can grow very large, it receives a bounded goal-relevant command subset rather than the complete registry on every action loop.

The live controller proof completes an ordered File -> Edit menu task from visual state and action history rather than a fixed macro. A deterministic Task Policy gate now classifies each planned action as reversible UI, project mutation, destructive, or ambiguous before Hands can execute it; ambiguous and unauthorized impacts fail closed. It also demonstrated recovery: when one Edit click did not produce the expected dropdown, the verifier rejected the result and the next loop re-observed and retried before declaring completion. Controller v1 also plans and executes semantically grounded reversible drags: a live proof moved the timeline playhead from 00s to 02s, verified the result visually, and then restored the playhead. See `docs/CONTROLLER_V1.md`.

## M4 live transaction gate

M4 now has a dedicated rollback-first real-AE proof at `scripts/prove_m4_transaction.py` and a first-class launcher action:

```powershell
.\editgpt.ps1 -Action proof-m4
```

The gate uses the registered native `layer.new.null` command as a bounded `layer_structure` mutation. It first forces visual verification failure and requires the controller-owned Undo path to restore the baseline. Only after that rollback succeeds does it prove a committed mutation, then clean up that committed proof mutation and verify the final visible state against the original baseline. The proof also requires the same `AfterFX.exe` process ID at the beginning and end.

M4 is not considered complete until the live proof writes `artifacts/m4-live-proof/proof.json` with `ok: true`. The software path and PowerShell entrypoint are covered by Windows CI; the real workstation execution is a separate gate.

## M5 source + temporal Eyes

M5 adds exact read-only source-video evidence independently of After Effects preview scaling. eyes_source_open, eyes_source_frame, eyes_source_frames, eyes_source_index_at_time, and related health/info/close operations expose exact decoded frames through the existing Eyes MCP. PyNvVideoCodec is preferred when its NVIDIA/CUDA runtime is healthy; PyAV is the compatibility fallback and preserves decoded-frame PTS for variable-frame-rate timing.

LocalQwenVLClient.observe_images(...) now accepts bounded, labeled chronological frame sequences so GPT can reason about visible temporal changes without continuous VLM inference. The first M5 proof validates exact frame retrieval, source-time lookup, and ordered multi-frame semantic understanding:

`powershell
.\editgpt.ps1 -Action proof-m5-source-temporal
`

The current workstation passes the proof through PyAV. PyNvVideoCodec is installed but its DLL cannot load because the required CUDA Toolkit runtime is not installed, so GPU source decode remains an environment optimization to restore rather than a correctness dependency.

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
.\editgpt.ps1 -Action proof-semantic-click
.\editgpt.ps1 -Action proof-hands-ui
.\editgpt.ps1 -Action proof-controller
.\editgpt.ps1 -Action proof-drag
.\editgpt.ps1 -Action proof-m4
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

## Design rules

- Use the strongest zero-recurring-cost tool that the available hardware can run reliably. Step down only for a real blocker such as hardware support, Windows compatibility, unacceptable latency, or integration failure.
- Reuse the current After Effects process by default. Restart or close AE only when a proof specifically requires lifecycle behavior, AE is unhealthy, or isolation cannot safely be restored in-process.
- **Do not redevelop an AE capability before checking AE-native commands.** Shortcut, Quick Apply, scripting API, and stable command-ID routes take precedence over custom UI tooling when they can perform the operation reliably.
- Keep Eyes as evidence, Hands as guarded transport, and project-mutation authority in the Controller/task-contract layer regardless of command transport.