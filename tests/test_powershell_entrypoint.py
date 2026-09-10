from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "editgpt.ps1"


def test_powershell_entrypoint_exposes_first_class_m4_proof() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert '"proof-m4"' in text
    assert "scripts\\prove_m4_transaction.py" in text
    assert "Wait-SemanticReady" in text
    assert "proof-m4 requires the semantic verifier" in text


@pytest.mark.skipif(os.name != "nt", reason="PowerShell syntax validation is Windows-specific")
def test_powershell_entrypoint_parses_on_windows() -> None:
    command = (
        "$ErrorActionPreference='Stop'; "
        f"[scriptblock]::Create((Get-Content -Raw -LiteralPath '{ENTRYPOINT}')) | Out-Null"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_entrypoint_exposes_m5_source_temporal_proof() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert '"proof-m5-source-temporal"' in text
    assert "proof m5-source-temporal" in text
