from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

MCP_HOST = "127.0.0.1"
MCP_PORT = 8765
HANDS_MCP_HOST = "127.0.0.1"
HANDS_MCP_PORT = 8766
SEMANTIC_HOST = "127.0.0.1"
SEMANTIC_PORT = 8080
SEMANTIC_MODELS_URL = f"http://{SEMANTIC_HOST}:{SEMANTIC_PORT}/v1/models"
SEMANTIC_MODEL = "Qwen/Qwen3-VL-8B-Instruct-GGUF:Q8_0"
SEMANTIC_CONTEXT = 8192
SEMANTIC_GPU_RESERVE_MIB = 4096


@dataclass(frozen=True)
class ProcessRecord:
    name: str
    pid: int
    command: list[str]
    log_path: str
    started_at_unix: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pid": self.pid,
            "command": self.command,
            "log_path": self.log_path,
            "started_at_unix": self.started_at_unix,
        }


class EditGPTOrchestrator:
    """Local EditGPT service/process supervisor.

    It intentionally does not restart or close After Effects. AE is treated as an
    external interactive application that should be reused unless a later proof
    explicitly requires lifecycle control.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or discover_repo_root()).resolve()
        self.runtime_dir = self.root / ".editgpt"
        self.logs_dir = self.runtime_dir / "logs"
        self.state_path = self.runtime_dir / "services.json"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict[str, Any]:
        services = self._load_service_state()
        return {
            "type": "editgpt_orchestrator_status",
            "repo_root": str(self.root),
            "git_head": _git_output(self.root, ["rev-parse", "HEAD"]),
            "git_dirty": bool(_git_output(self.root, ["status", "--porcelain"])),
            "after_effects_running": _after_effects_running(),
            "services": {
                "eyes_mcp": {
                    "ready": _port_open(MCP_HOST, MCP_PORT),
                    "endpoint": f"http://{MCP_HOST}:{MCP_PORT}/mcp",
                    "record": services.get("eyes_mcp"),
                },
                "hands_mcp": {
                    "ready": _port_open(HANDS_MCP_HOST, HANDS_MCP_PORT),
                    "endpoint": f"http://{HANDS_MCP_HOST}:{HANDS_MCP_PORT}/mcp",
                    "write_capable": True,
                    "record": services.get("hands_mcp"),
                },
                "semantic_qwen": {
                    "ready": _http_json_ready(SEMANTIC_MODELS_URL),
                    "endpoint": SEMANTIC_MODELS_URL,
                    "model": SEMANTIC_MODEL,
                    "record": services.get("semantic_qwen"),
                },
            },
            "artifacts": self._artifact_summary(),
        }

    def up(self, *, with_semantic: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "eyes_mcp": self.start_eyes_mcp(),
            "hands_mcp": self.start_hands_mcp(),
        }
        if with_semantic:
            result["semantic_qwen"] = self.start_semantic_qwen()
        result["status"] = self.status()
        return result

    def start_eyes_mcp(self, *, wait_s: float = 12.0) -> dict[str, Any]:
        if _port_open(MCP_HOST, MCP_PORT):
            return {"ok": True, "started": False, "reason": "already_listening"}

        command = [
            sys.executable,
            "-m",
            "editgpt.mcp_server",
            "--transport",
            "streamable-http",
            "--host",
            MCP_HOST,
            "--port",
            str(MCP_PORT),
        ]
        record = self._spawn("eyes_mcp", command)
        if _wait_until(lambda: _port_open(MCP_HOST, MCP_PORT), wait_s):
            return {"ok": True, "started": True, **record.as_dict()}
        return {
            "ok": False,
            "started": True,
            "reason": "listener_did_not_become_ready",
            **record.as_dict(),
            "log_tail": self.log_tail("eyes_mcp"),
        }

    def start_hands_mcp(self, *, wait_s: float = 12.0) -> dict[str, Any]:
        if _port_open(HANDS_MCP_HOST, HANDS_MCP_PORT):
            return {"ok": True, "started": False, "reason": "already_listening"}

        command = [
            sys.executable,
            "-m",
            "editgpt.hands_mcp_server",
            "--transport",
            "streamable-http",
            "--host",
            HANDS_MCP_HOST,
            "--port",
            str(HANDS_MCP_PORT),
        ]
        record = self._spawn("hands_mcp", command)
        if _wait_until(lambda: _port_open(HANDS_MCP_HOST, HANDS_MCP_PORT), wait_s):
            return {"ok": True, "started": True, **record.as_dict()}
        return {
            "ok": False,
            "started": True,
            "reason": "listener_did_not_become_ready",
            **record.as_dict(),
            "log_tail": self.log_tail("hands_mcp"),
        }

    def start_semantic_qwen(self, *, wait_s: float = 15.0) -> dict[str, Any]:
        if _http_json_ready(SEMANTIC_MODELS_URL):
            return {"ok": True, "started": False, "reason": "already_ready"}

        command = _llama_server_command()
        if command is None:
            return {
                "ok": False,
                "started": False,
                "reason": "llama_cpp_not_installed",
                "setup": r"powershell -ExecutionPolicy Bypass -File .\scripts\setup_semantic_windows.ps1",
            }

        record = self._spawn("semantic_qwen", command)
        ready = _wait_until(lambda: _http_json_ready(SEMANTIC_MODELS_URL), wait_s, interval_s=0.5)
        return {
            "ok": ready or _process_alive(record.pid),
            "ready": ready,
            "started": True,
            "state": "ready" if ready else "starting",
            "note": None
            if ready
            else "The first model download/load can take several minutes; the service is continuing in the background.",
            **record.as_dict(),
            "log_tail": None if ready else self.log_tail("semantic_qwen", lines=12),
        }

    def wait_for_semantic(self, *, timeout_s: float = 900.0) -> bool:
        if _http_json_ready(SEMANTIC_MODELS_URL):
            return True
        print(
            f"Waiting up to {timeout_s:g}s for local Qwen to download/load. "
            f"Log: {self.logs_dir / 'semantic_qwen.log'}"
        )
        deadline = time.perf_counter() + timeout_s
        next_notice = time.perf_counter() + 15.0
        while time.perf_counter() < deadline:
            if _http_json_ready(SEMANTIC_MODELS_URL):
                return True
            if time.perf_counter() >= next_notice:
                print("Qwen is still starting...")
                next_notice = time.perf_counter() + 15.0
            time.sleep(0.5)
        return False

    def down(self) -> dict[str, Any]:
        results = {
            "eyes_mcp": self._stop_known_process("eyes_mcp"),
            "hands_mcp": self._stop_known_process("hands_mcp"),
            "semantic_qwen": self._stop_known_process("semantic_qwen"),
        }
        return {"type": "editgpt_orchestrator_down", "results": results}

    def doctor(self) -> int:
        commands = [
            [sys.executable, "-m", "pytest"],
            [sys.executable, str(self.root / "scripts" / "check_env.py")],
        ]
        for command in commands:
            completed = subprocess.run(command, cwd=self.root, check=False)
            if completed.returncode != 0:
                return int(completed.returncode or 1)
        print(json.dumps(self.status(), indent=2))
        return 0

    def proof(self, name: str) -> int:
        scripts = {
            "capture": self.root / "scripts" / "probe_capture_modes.py",
            "mcp": self.root / "scripts" / "prove_mcp.py",
            "hands": self.root / "scripts" / "prove_hands.py",
            "loop": self.root / "scripts" / "prove_observe_act_verify.py",
            "semantic-pointer": self.root / "scripts" / "prove_semantic_pointer.py",
            "semantic-click": self.root / "scripts" / "prove_semantic_click.py",
            "semantic": self.root / "scripts" / "prove_semantic.py",
        }
        if name not in scripts:
            raise ValueError(f"unknown proof: {name}")

        if name == "mcp":
            start = self.start_eyes_mcp()
            if not start.get("ok"):
                print(json.dumps(start, indent=2))
                return 2
        elif name == "hands":
            start = self.start_hands_mcp()
            if not start.get("ok"):
                print(json.dumps(start, indent=2))
                return 5
        elif name == "loop":
            for start in (self.start_eyes_mcp(), self.start_hands_mcp()):
                if not start.get("ok"):
                    print(json.dumps(start, indent=2))
                    return 6
        elif name in {"semantic-pointer", "semantic-click"}:
            for start in (self.start_eyes_mcp(), self.start_hands_mcp(), self.start_semantic_qwen()):
                if not start.get("ok"):
                    print(json.dumps(start, indent=2))
                    return 7
            if not self.wait_for_semantic():
                return 8
        elif name == "semantic":
            start = self.start_semantic_qwen()
            if not start.get("ok"):
                print(json.dumps(start, indent=2))
                return 3
            if not self.wait_for_semantic():
                print("ERROR: semantic server did not become ready before timeout.")
                print(self.log_tail("semantic_qwen", lines=30))
                return 4

        completed = subprocess.run([sys.executable, str(scripts[name])], cwd=self.root, check=False)
        return int(completed.returncode)

    def log_tail(self, service: str, *, lines: int = 40) -> str:
        path = self.logs_dir / f"{service}.log"
        if not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return f"unable to read log: {exc}"
        return "\n".join(content[-max(1, lines) :])

    def _spawn(self, name: str, command: list[str]) -> ProcessRecord:
        log_path = self.logs_dir / f"{name}.log"
        log_handle = log_path.open("ab", buffering=0)
        kwargs: dict[str, Any] = {
            "cwd": str(self.root),
            "stdin": subprocess.DEVNULL,
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(command, **kwargs)
        finally:
            log_handle.close()

        record = ProcessRecord(
            name=name,
            pid=process.pid,
            command=command,
            log_path=str(log_path),
            started_at_unix=time.time(),
        )
        state = self._load_service_state()
        state[name] = record.as_dict()
        self._save_service_state(state)
        return record

    def _stop_known_process(self, name: str) -> dict[str, Any]:
        state = self._load_service_state()
        record = state.get(name)
        if not record or not isinstance(record.get("pid"), int):
            return {"ok": True, "stopped": False, "reason": "no_known_process"}
        pid = int(record["pid"])
        if not _process_alive(pid):
            state.pop(name, None)
            self._save_service_state(state)
            return {"ok": True, "stopped": False, "reason": "already_exited", "pid": pid}

        try:
            if os.name == "nt":
                completed = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                ok = completed.returncode == 0
                detail = (completed.stdout or completed.stderr).strip()
            else:
                os.kill(pid, signal.SIGTERM)
                ok = True
                detail = "SIGTERM sent"
        except OSError as exc:
            ok = False
            detail = f"{type(exc).__name__}: {exc}"

        if ok:
            state.pop(name, None)
            self._save_service_state(state)
        return {"ok": ok, "stopped": ok, "pid": pid, "detail": detail}

    def _artifact_summary(self) -> dict[str, Any]:
        root = self.root / "artifacts"
        if not root.exists():
            return {"root": str(root), "directories": []}
        dirs: list[dict[str, Any]] = []
        for directory in sorted(path for path in root.iterdir() if path.is_dir()):
            files = [path.name for path in directory.iterdir() if path.is_file()]
            dirs.append({"name": directory.name, "files": sorted(files)})
        return {"root": str(root), "directories": dirs}

    def _load_service_state(self) -> dict[str, dict[str, Any]]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        services = data.get("services") if isinstance(data, dict) else None
        return services if isinstance(services, dict) else {}

    def _save_service_state(self, services: dict[str, dict[str, Any]]) -> None:
        payload = {"version": 1, "services": services}
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)


def discover_repo_root(start: Path | None = None) -> Path:
    candidate = (start or Path.cwd()).resolve()
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=candidate,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0 and completed.stdout.strip():
        return Path(completed.stdout.strip())
    if (candidate / "pyproject.toml").exists():
        return candidate
    raise RuntimeError("EditGPT repository root could not be located")


def _git_output(root: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _port_open(host: str, port: int, timeout_s: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _http_json_ready(url: str, timeout_s: float = 1.0) -> bool:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            if response.status != 200:
                return False
            json.loads(response.read().decode("utf-8"))
            return True
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False


def _wait_until(predicate: Callable[[], bool], timeout_s: float, *, interval_s: float = 0.2) -> bool:
    deadline = time.perf_counter() + max(0.0, timeout_s)
    while time.perf_counter() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return predicate()


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _after_effects_running() -> bool | None:
    if os.name != "nt":
        return None
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq AfterFX.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return "AfterFX.exe" in completed.stdout


def _llama_server_command() -> list[str] | None:
    server = shutil.which("llama-server")
    if server:
        prefix = [server]
    else:
        llama = shutil.which("llama")
        if not llama:
            return None
        prefix = [llama, "serve"]
    return [
        *prefix,
        "-hf",
        SEMANTIC_MODEL,
        "--host",
        SEMANTIC_HOST,
        "--port",
        str(SEMANTIC_PORT),
        "-ngl",
        "all",
        "-c",
        str(SEMANTIC_CONTEXT),
        "--fit",
        "on",
        "--fit-target",
        str(SEMANTIC_GPU_RESERVE_MIB),
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="editgpt-control")
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="start current EditGPT local services")
    up.add_argument("--no-semantic", action="store_true", help="start MCP services only")

    sub.add_parser("status", help="show repo, AE, service, and artifact status")
    sub.add_parser("down", help="stop only services previously started by EditGPT")
    sub.add_parser("doctor", help="run tests/environment checks and print status")

    proof = sub.add_parser("proof", help="run one current proof")
    proof.add_argument("name", choices=("capture", "mcp", "hands", "loop", "semantic-pointer", "semantic-click", "semantic"))

    logs = sub.add_parser("logs", help="show the tail of a managed service log")
    logs.add_argument("service", choices=("eyes_mcp", "hands_mcp", "semantic_qwen"))
    logs.add_argument("--lines", type=int, default=40)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    orchestrator = EditGPTOrchestrator()

    if args.command == "up":
        print(json.dumps(orchestrator.up(with_semantic=not args.no_semantic), indent=2))
        return 0
    if args.command == "status":
        print(json.dumps(orchestrator.status(), indent=2))
        return 0
    if args.command == "down":
        print(json.dumps(orchestrator.down(), indent=2))
        return 0
    if args.command == "doctor":
        return orchestrator.doctor()
    if args.command == "proof":
        return orchestrator.proof(args.name)
    if args.command == "logs":
        print(orchestrator.log_tail(args.service, lines=max(1, args.lines)))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
