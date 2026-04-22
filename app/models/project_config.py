from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ProjectConfig:
    project_name: str = 'campaign_openfoam_v02'
    base_case_dir: Path | None = None
    primary_csv: Path | None = None
    secondary_csv: Path | None = None
    output_dir: Path | None = None
    runner_mode: str = 'internal'
    default_solver: str = 'foamRun'
    n_processors: int = 1
    directory_prefix: str = 'case_'
    log_prefix: str = 'log_'
    keep_open_when_finished: bool = True
    shell_executable: str = ''
    activation_enabled: bool = False
    activation_mode: str = 'none'
    activation_command: str = ''
    bashrc_path: str = '~/.bashrc'
    internal_setup_commands: list[str] = field(default_factory=lambda: ['blockMesh'])
    internal_stage_commands: list[str] = field(default_factory=lambda: ['foamRun'])
    internal_post_commands: list[str] = field(default_factory=list)
    plot_time_stride: float = 0.0
    plot_iteration_stride: int = 1

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key, value in list(payload.items()):
            if isinstance(value, Path):
                payload[key] = str(value)
        hidden_keys = {
            'runner_mode',
            'default_solver',
            'n_processors',
            'shell_executable',
            'activation_enabled',
            'activation_mode',
            'activation_command',
            'bashrc_path',
        }
        for key in hidden_keys:
            payload.pop(key, None)
        return payload
