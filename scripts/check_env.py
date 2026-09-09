from __future__ import annotations

import importlib.util
import json
import platform
import shutil


def present(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


report = {
    "platform": platform.platform(),
    "python": platform.python_version(),
    "ffmpeg": shutil.which("ffmpeg"),
    "nvidia_smi": shutil.which("nvidia-smi"),
    "python_modules": {
        "numpy": present("numpy"),
        "cv2": present("cv2"),
        "dxcam": present("dxcam"),
        "torch": present("torch"),
        "transformers": present("transformers"),
        "av": present("av"),
    },
}
print(json.dumps(report, indent=2))
