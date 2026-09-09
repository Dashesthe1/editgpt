from __future__ import annotations

import importlib.util
import json
import platform
import shutil
import subprocess
from typing import Any


def present(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def command_output(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or completed.stderr).strip()
    return output or None


def nvidia_gpus() -> list[dict[str, Any]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return []
    output = command_output(
        [
            executable,
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if not output:
        return []
    gpus: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        name, total_mib, free_mib, driver = parts
        try:
            total = int(float(total_mib))
            free = int(float(free_mib))
        except ValueError:
            continue
        gpus.append(
            {
                "name": name,
                "memory_total_mib": total,
                "memory_free_mib": free,
                "driver_version": driver,
            }
        )
    return gpus


report = {
    "platform": platform.platform(),
    "python": platform.python_version(),
    "ffmpeg": shutil.which("ffmpeg"),
    "nvidia_smi": shutil.which("nvidia-smi"),
    "gpus": nvidia_gpus(),
    "python_modules": {
        "numpy": present("numpy"),
        "cv2": present("cv2"),
        "dxcam": present("dxcam"),
        "mcp": present("mcp"),
        "torch": present("torch"),
        "transformers": present("transformers"),
        "av": present("av"),
        "PyNvVideoCodec": present("PyNvVideoCodec"),
    },
}
print(json.dumps(report, indent=2))
