from __future__ import annotations

import json
from pathlib import Path

import av
import cv2
import numpy as np

from editgpt.eyes.semantic import LocalQwenVLClient
from editgpt.eyes.source import open_video_source, source_backend_health

OUTPUT_DIR = Path("artifacts/m5-source-temporal-proof")
SOURCE_PATH = OUTPUT_DIR / "fixture.mp4"

PROMPT = """You are EditGPT's temporal visual sensor.
The images are source-video frames in chronological order and each image contains a large visible state label.
Return JSON only with keys: ordered_states, changed, confidence, uncertainty.
ordered_states must list the visible state labels in chronological order with duplicates removed.
changed must be true if the visible state changes across the sequence.
Do not infer labels that are not visibly present."""


def make_fixture() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with av.open(str(SOURCE_PATH), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width = 640
        stream.height = 360
        stream.pix_fmt = "yuv420p"
        for index in range(15):
            if index < 5:
                label, value = "STATE A", 40
            elif index < 10:
                label, value = "STATE B", 125
            else:
                label, value = "STATE C", 215
            image = np.full((360, 640, 3), value, dtype=np.uint8)
            cv2.putText(image, label, (115, 205), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 5, cv2.LINE_AA)
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(cleaned)


def main() -> int:
    make_fixture()
    health = source_backend_health()
    reader = open_video_source(SOURCE_PATH, prefer_gpu=True)
    frames = reader.read_frames([1, 6, 11])
    labels = [f"index={f.frame_id} time={f.metadata['source_time_s']:.3f}s" for f in frames]
    qwen = LocalQwenVLClient()
    semantic_health = qwen.health()
    payload = {
        "type": "editgpt_m5_source_temporal_proof",
        "source_backend_health": health,
        "source_metadata": reader.metadata.as_dict(),
        "sampled_frames": labels,
        "semantic_server": semantic_health,
        "checks": {},
    }
    payload["checks"]["exact_indices"] = [f.frame_id for f in frames] == [1, 6, 11]
    payload["checks"]["monotonic_source_time"] = [f.metadata["source_time_s"] for f in frames] == sorted(f.metadata["source_time_s"] for f in frames)
    payload["checks"]["time_lookup"] = reader.index_at_seconds(0.55) == 6
    if not semantic_health.get("ok"):
        payload["error"] = "local Qwen semantic server is not ready"
    else:
        obs = qwen.observe_images([f.image for f in frames], prompt=PROMPT, labels=labels, source=str(SOURCE_PATH))
        payload["semantic"] = obs.as_dict()
        try:
            parsed = parse_json(obs.text)
        except Exception as exc:
            parsed = {"parse_error": f"{type(exc).__name__}: {exc}"}
        payload["semantic_parsed"] = parsed
        payload["checks"]["ordered_states"] = parsed.get("ordered_states") == ["STATE A", "STATE B", "STATE C"]
        payload["checks"]["change_detected"] = parsed.get("changed") is True
    reader.close()
    payload["ok"] = bool(payload["checks"]) and all(payload["checks"].values())
    (OUTPUT_DIR / "proof.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for frame in frames:
        cv2.imwrite(str(OUTPUT_DIR / f"frame_{frame.frame_id:03d}.jpg"), frame.image)
    print(json.dumps(payload, indent=2))
    print(f"Evidence written to: {OUTPUT_DIR.resolve()}")
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
