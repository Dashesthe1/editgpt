from __future__ import annotations

from pathlib import Path

from editgpt.orchestrator import (
    EditGPTOrchestrator,
    SEMANTIC_GPU_RESERVE_MIB,
    SEMANTIC_MODEL,
    _llama_server_command,
)


def test_llama_server_command_prefers_server_binary(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        if name == "llama-server":
            return r"C:\tools\llama-server.exe"
        return None

    monkeypatch.setattr("editgpt.orchestrator.shutil.which", fake_which)
    command = _llama_server_command()
    assert command is not None
    assert command[0].endswith("llama-server.exe")
    assert "-hf" in command
    assert SEMANTIC_MODEL in command
    assert "--fit-target" in command
    assert str(SEMANTIC_GPU_RESERVE_MIB) in command


def test_llama_server_command_falls_back_to_llama_serve(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        if name == "llama":
            return r"C:\tools\llama.exe"
        return None

    monkeypatch.setattr("editgpt.orchestrator.shutil.which", fake_which)
    command = _llama_server_command()
    assert command is not None
    assert command[:2] == [r"C:\tools\llama.exe", "serve"]


def test_service_state_round_trip_is_local(tmp_path: Path) -> None:
    orchestrator = EditGPTOrchestrator(root=tmp_path)
    services = {
        "eyes_mcp": {
            "pid": 123,
            "name": "eyes_mcp",
            "command": ["python", "-m", "editgpt.mcp_server"],
            "log_path": "example.log",
            "started_at_unix": 1.0,
        }
    }
    orchestrator._save_service_state(services)
    assert orchestrator._load_service_state() == services
    assert orchestrator.state_path.parent == tmp_path / ".editgpt"


def test_artifact_summary_lists_evidence_without_reading_contents(tmp_path: Path) -> None:
    proof = tmp_path / "artifacts" / "semantic-proof"
    proof.mkdir(parents=True)
    (proof / "semantic_result.json").write_text("{}", encoding="utf-8")
    orchestrator = EditGPTOrchestrator(root=tmp_path)
    summary = orchestrator._artifact_summary()
    assert summary["directories"] == [
        {"name": "semantic-proof", "files": ["semantic_result.json"]}
    ]


def test_cli_accepts_hands_ui_proof() -> None:
    from editgpt.orchestrator import build_parser

    args = build_parser().parse_args(["proof", "hands-ui"])
    assert args.command == "proof"
    assert args.name == "hands-ui"
