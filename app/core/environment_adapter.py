from __future__ import annotations

import os
import platform
import shlex
from pathlib import Path

from app.models.project_config import ProjectConfig


class EnvironmentAdapter:
    """Camada para adaptar chamadas ao ambiente Windows + WSL/OpenFOAM."""

    def running_inside_wsl(self) -> bool:
        if 'WSL_DISTRO_NAME' in os.environ:
            return True
        rel = platform.release().lower()
        version = platform.version().lower()
        return 'microsoft' in rel or 'microsoft' in version

    def shell_prefix(self, config: ProjectConfig, *, interactive: bool = False) -> list[str]:
        shell = config.shell_executable.strip()
        shell_flag = '-ic' if interactive else '-lc'

        if self.running_inside_wsl():
            if not shell or shell.lower() == 'wsl':
                return ['bash', shell_flag]
            tokens = shlex.split(shell)
            return tokens + [shell_flag]

        if not shell:
            return ['wsl', 'bash', shell_flag]
        tokens = shlex.split(shell)
        if len(tokens) == 1 and tokens[0].lower() == 'wsl':
            return ['wsl', 'bash', shell_flag]
        return tokens + [shell_flag]

    def quote_path(self, path: Path) -> str:
        return str(path).replace('\\', '/')

    def requires_interactive_shell(self, config: ProjectConfig) -> bool:
        return bool(config.activation_enabled and config.activation_mode == 'alias_or_function')

    def build_activation_lines(self, config: ProjectConfig) -> list[str]:
        if not config.activation_enabled or config.activation_mode == 'none':
            return []

        mode = config.activation_mode.strip().lower()
        command = config.activation_command.strip()
        if mode == 'alias_or_function':
            if not command:
                raise ValueError('Modo alias/função habilitado, mas nenhum comando de ativação foi informado.')
            bashrc = config.bashrc_path.strip() or '~/.bashrc'
            return [f'source {bashrc} >/dev/null 2>&1', 'shopt -s expand_aliases', command]
        if mode == 'source_command':
            if not command:
                raise ValueError('Modo source command habilitado, mas nenhum comando de ativação foi informado.')
            return [command]
        return []

    def sanitize_label(self, text: str) -> str:
        cleaned = ''.join(ch if ch.isalnum() or ch in {'_', '-'} else '_' for ch in text.strip())
        cleaned = cleaned.strip('_')
        return cleaned or 'command'
