from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != "nt", reason="Windows installer scripts")
def test_bootstrap_plan_is_non_destructive_and_serializable(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "install-bootstrap.ps1"
    data_root = tmp_path / "workspace"
    downloads_root = tmp_path / "downloads"
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Mode",
            "Standard",
            "-InstallRoot",
            str(ROOT),
            "-DataRoot",
            str(data_root),
            "-DownloadsRoot",
            str(downloads_root),
            "-InstallWebView",
            "-InstallOllama",
            "-DownloadModel",
            "-PlanOnly",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(result.stdout)
    assert plan["mode"] == "Standard"
    assert plan["model"] == "llama3.2:3b"
    assert plan["install_webview"] is True
    assert plan["install_ollama"] is True
    assert plan["download_model"] is True
    assert not data_root.exists()
    assert not downloads_root.exists()


def test_inno_setup_defines_install_and_uninstall_workflows() -> None:
    definition = (ROOT / "installer" / "Leadroom.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in definition
    assert "ArchitecturesAllowed=x64compatible" in definition
    assert "install-bootstrap.ps1" in definition
    assert "clean-install-state.ps1" in definition
    assert "CreateInputDirPage" in definition
    assert "Leadroom-Setup" in definition
    assert "-ProcessPath" in definition
    assert "IsProcessRunning(BootstrapProcessId)" in definition
    assert "stopped unexpectedly" in definition


def test_bootstrap_long_running_children_are_cancellable() -> None:
    definition = (ROOT / "scripts" / "install-bootstrap.ps1").read_text(encoding="utf-8")
    assert "[string]$ProcessPath" in definition
    assert "Invoke-CancellableProcess $winget" in definition
    assert "Stop-InstallerProcessTree $process" in definition
    assert 'Invoke-CancellableProcess $powershell $setupArguments' in definition
    assert 'Invoke-CancellableProcess $powershell $importArguments' in definition
    assert "$reader.ReadLineAsync()" in definition
    assert "while (-not $readTask.Wait(250))" in definition
    assert "while (-not $reader.EndOfStream)" not in definition
    assert "while (-not $sendTask.Wait(250))" in definition
    assert "Stop-InstallerProcessTree $started" in definition
    assert "Assert-Capacity $ubuntuStorage 30GB" in definition


@pytest.mark.parametrize(
    "script_name",
    ["setup-local-data.ps1", "import-osm.ps1", "setup-local-updates.ps1"],
)
def test_full_local_scripts_fail_fast_on_native_command_errors(script_name: str) -> None:
    definition = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
    assert "function Assert-NativeSuccess" in definition
    assert definition.count("Assert-NativeSuccess") >= 3


@pytest.mark.skipif(os.name != "nt", reason="Windows cleanup script")
def test_cleanup_refuses_to_run_without_confirmation() -> None:
    script = ROOT / "scripts" / "clean-install-state.ps1"
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Cleanup is destructive" in (result.stdout + result.stderr)
