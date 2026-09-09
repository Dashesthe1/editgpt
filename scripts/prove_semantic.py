from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import cv2

from editgpt.eyes.semantic import LocalQwenVLClient


PROMPT = """You are the semantic visual sensor for EditGPT, a professional video-editing system.
Analyze this single After Effects screenshot strictly from visible evidence.
Return concise JSON with these keys:
- application
- visible_media
- subjects_and_objects
- composition
- visible_text
- ae_ui_state
- editing_relevant_details
- uncertainty

Rules:
1. Be specific about what is actually visible.
2. Do not invent motion or events that require seeing earlier/later frames.
3. Distinguish visible evidence from uncertainty.
4. Mention important framing, subject placement, occlusion, blur, lighting/color, and any readable AE UI state.
5. Do not wrap the JSON in markdown fences.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove local Qwen semantic sight on a captured AE frame.")
    parser.add_argument(
        "--image",
        default="artifacts/capture-mode-probe/truthful_latest.jpg",
        help="AE screenshot to analyze",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--output-dir", default="artifacts/semantic-proof")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"ERROR: image does not exist: {image_path.resolve()}")
        return 2

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        print(f"ERROR: OpenCV could not decode: {image_path.resolve()}")
        return 3

    client = LocalQwenVLClient(base_url=args.base_url)
    health = client.health()
    print(json.dumps({"semantic_server": health}, indent=2))
    if not health.get("ok"):
        print("ERROR: local Qwen server is not ready.")
        print("Start it in another PowerShell window with:")
        print("  llama serve -hf Qwen/Qwen3-VL-8B-Instruct-GGUF:Q8_0 --host 127.0.0.1 --port 8080 -ngl 99 -c 8192")
        return 4

    observation = client.observe(
        image,
        prompt=PROMPT,
        source=str(image_path),
        max_tokens=500,
        max_width=1280,
        jpeg_quality=92,
    )

    result = {
        "ok": bool(observation.text.strip()),
        "observation": observation.as_dict(),
        "source_image": str(image_path),
    }
    (output / "semantic_result.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    shutil.copy2(image_path, output / "source.jpg")

    print(json.dumps(result, indent=2))
    print(f"Evidence written to: {output.resolve()}")
    return 0 if result["ok"] else 5


if __name__ == "__main__":
    raise SystemExit(main())
