# EditGPT Eyes v1

## Definition of complete

Eyes v1 is complete only when GPT can obtain accurate visual evidence for the classes of questions a professional editor needs, without depending on continuous 60 Hz LLM inference.

Required capabilities:

1. Live After Effects/window observation.
2. Exact source-frame access independent of preview scaling.
3. Semantic understanding of subjects, actions, expressions, composition, camera behavior, and visible UI.
4. Temporal event localization: start/stop, impacts, extrema, acceleration, appearance/disappearance, occlusion, and transitions.
5. Arbitrary object and point tracking.
6. Pixel-level segmentation/mattes across video.
7. Motion measurement and camera-vs-subject motion separation.
8. Shot/cut/fade detection.
9. Exact-frame inspection and sequence comparison.
10. Short-term visual memory with timestamps/frame IDs.
11. Confidence/uncertainty reporting.
12. Evidence retrieval: GPT can request the actual relevant frame(s), not only prose.

## Architecture

```text
After Effects live window ── DXcam ───────┐
                                         │
Original footage ─ PyNvVideoCodec/PyAV ──┼── FrameStore / timeline clock
                                         │
                                         ├── Qwen3-VL      semantic eye
                                         ├── SAM 3.1       mask/object eye
                                         ├── TAPNext++     point-tracking eye
                                         ├── NVIDIA OF     reflex motion eye
                                         ├── OpenCV        measurements/fallback
                                         └── shot detector structure eye
                                                  │
                                                  ▼
                                             EyesService
                                                  │
                                                  ▼
                                                 GPT
```

## Attention model

Not every expensive model should run on every frame.

- Always-on: capture, timestamps, bounded frame buffer, inexpensive change/motion signals.
- Periodic/on-change: semantic vision.
- On-demand: SAM 3.1 segmentation/tracking, TAPNext++ point tracking, deeper Qwen inspection.
- High-rate on-demand: motion/reflex measurements.

This preserves every frame while only spending expensive inference where GPT's current editing question requires it.

## Stable API goals

The service should converge on operations such as:

- `observe(...)`
- `inspect_frames(...)`
- `find_event(...)`
- `track_point(...)`
- `track_object(...)`
- `segment(...)`
- `measure_motion(...)`
- `compare(...)`
- `health()`

Backends remain replaceable. A new model should not require redesigning GPT-facing contracts.

## AE Command Surface integration — M1

M1 remains strictly read-only, but it participates in the shared AE command-first architecture as the **evidence layer**.

When an Eyes proof or later controller needs AE placed into an inspectable state, the surrounding harness should prefer the shared registered command surface over manually finding UI controls. Examples include opening Project or Effects & Presets, revealing Scale or Mask Path, toggling the Graph Editor, moving exactly one frame, fitting the viewer, or switching between Composition and Timeline focus.

The separation is important:

- Eyes never sends the command itself and never gains write authority.
- Hands or the controller executes the registered command.
- Eyes captures fresh evidence after the command and verifies the intended visible state.
- If a perception test repeatedly needs an AE state, add/reuse a command recipe instead of building a new perception-specific UI driver.

This makes M1 tests faster and more deterministic without weakening the Eyes security boundary. See `docs/AE_COMMAND_SURFACE_V1.md`.

## Validation gates

Eyes cannot be called complete until real-video tests pass for:

- semantic action recognition;
- exact event localization;
- point tracking;
- recovery after occlusion;
- subject segmentation across motion;
- motion/camera separation;
- cuts/transitions;
- composition inspection;
- exact source-frame retrieval;
- visible AE state understanding;
- reference-vs-candidate comparison;
- uncertainty escalation rather than confident fabrication.
