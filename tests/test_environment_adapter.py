from __future__ import annotations

from pathlib import Path

from app.core.environment_adapter import EnvironmentAdapter
from app.models.project_config import ProjectConfig


def test_environment_adapter_host_and_bash():
    adapter = EnvironmentAdapter()
    host = adapter.host_kind()
    assert host in {"linux", "macos", "windows", "wsl"}
    bash = adapter.resolve_bash()
    assert "bash" in bash


def test_environment_adapter_sanitize_label():
    adapter = EnvironmentAdapter()
    assert adapter.sanitize_label("blockMesh") == "blockMesh"
    assert adapter.sanitize_label("foamRun --parallel") == "foamRun_--parallel"
    assert adapter.sanitize_label("  ") == "command"


def test_environment_adapter_to_wsl_path():
    adapter = EnvironmentAdapter()
    windows_path = Path("C:/Users/bruno/case_001/script.sh")
    wsl_p = adapter.to_wsl_path(windows_path)
    # Deve converter letra de unidade Windows C: -> /mnt/c
    assert wsl_p.startswith("/mnt/c")


def test_environment_adapter_build_activation_lines():
    adapter = EnvironmentAdapter()
    config = ProjectConfig(
        activation_enabled=True,
        activation_mode="source_command",
        activation_command="source /opt/openfoam/etc/bashrc",
    )
    lines = adapter.build_activation_lines(config)
    assert any("source /opt/openfoam/etc/bashrc" in line for line in lines)
