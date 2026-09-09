from __future__ import annotations

import glob
import os
import platform
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.models.project_config import ProjectConfig


@dataclass(slots=True)
class OpenFOAMProbe:
    ok: bool
    host: str
    bash: str
    foam_run: str
    project_dir: str
    version: str
    detail: str


class EnvironmentAdapter:
    """Adapta a execução de comandos OpenFOAM ao host: macOS, Linux, WSL ou Windows."""

    def host_kind(self) -> str:
        if self.running_inside_wsl():
            return 'wsl'
        system = platform.system()
        if system == 'Darwin':
            return 'macos'
        if system == 'Linux':
            return 'linux'
        if system == 'Windows':
            return 'windows'
        return system.lower() or 'unknown'

    def running_inside_wsl(self) -> bool:
        if 'WSL_DISTRO_NAME' in os.environ:
            return True
        rel = platform.release().lower()
        version = platform.version().lower()
        return 'microsoft' in rel or 'microsoft' in version

    def is_native_unix(self) -> bool:
        return self.host_kind() in {'macos', 'linux'}

    def resolve_bash(self) -> str:
        if self.host_kind() == 'macos':
            for candidate in ('/opt/homebrew/bin/bash', '/usr/local/bin/bash'):
                if Path(candidate).is_file():
                    return candidate
        found = shutil.which('bash')
        if found:
            return found
        return '/bin/bash'

    def shell_prefix(self, config: ProjectConfig, *, interactive: bool = False) -> list[str]:
        shell = config.shell_executable.strip()
        login = self._uses_login_shell()
        if interactive:
            shell_flag = '-ic'
        elif login:
            shell_flag = '-lc'
        else:
            shell_flag = '-c'

        if self.running_inside_wsl():
            if not shell or shell.lower() == 'wsl':
                return [self.resolve_bash(), shell_flag]
            tokens = shlex.split(shell)
            return tokens + [shell_flag]

        if self.is_native_unix():
            if not shell or shell.lower() == 'wsl':
                return [self.resolve_bash(), shell_flag]
            tokens = shlex.split(shell)
            if len(tokens) == 1 and tokens[0].lower() == 'wsl':
                return [self.resolve_bash(), shell_flag]
            return tokens + [shell_flag]

        if not shell:
            return ['wsl', 'bash', shell_flag]
        tokens = shlex.split(shell)
        if len(tokens) == 1 and tokens[0].lower() == 'wsl':
            return ['wsl', 'bash', shell_flag]
        return tokens + [shell_flag]

    def quote_path(self, path: Path) -> str:
        target = path.resolve() if self.is_native_unix() else path
        posix = str(target).replace('\\', '/')
        return shlex.quote(posix)

    def requires_interactive_shell(self, config: ProjectConfig) -> bool:
        return bool(config.activation_enabled and config.activation_mode == 'alias_or_function')

    def build_environment_prelude(self) -> list[str]:
        if self.host_kind() != 'macos':
            return []
        return [
            'for _interfaceof_path in /opt/homebrew/bin /usr/local/bin; do',
            '    case ":${PATH:-}:" in',
            '        *":${_interfaceof_path}:"*) ;;',
            '        *) PATH="${PATH:+${PATH}:}${_interfaceof_path}" ;;',
            '    esac',
            'done',
            'export PATH',
            'unset _interfaceof_path',
        ]

    def build_activation_lines(self, config: ProjectConfig) -> list[str]:
        lines = list(self.build_environment_prelude())
        if not config.activation_enabled or config.activation_mode == 'none':
            return lines

        mode = config.activation_mode.strip().lower()
        command = self.normalize_activation_command(config.activation_command)
        if mode == 'alias_or_function':
            if not command:
                raise ValueError('Modo alias/função habilitado, mas nenhum comando de ativação foi informado.')
            bashrc = config.bashrc_path.strip() or '~/.bashrc'
            lines.extend([f'source {bashrc} >/dev/null 2>&1', 'shopt -s expand_aliases', command])
            return lines
        if mode == 'source_command':
            if not command:
                raise ValueError('Modo source command habilitado, mas nenhum comando de ativação foi informado.')
            lines.append(command)
            return lines
        return lines

    def normalize_activation_command(self, command: str) -> str:
        text = command.strip()
        if not text:
            return text
        if text.startswith('source ') or text.startswith('. '):
            return text
        path = Path(text).expanduser()
        if path.is_file():
            return f'source {shlex.quote(str(path))}'
        return text

    def discover_openfoam_bashrc_paths(self) -> list[Path]:
        found: list[Path] = []
        wm = os.environ.get('WM_PROJECT_DIR', '').strip()
        if wm:
            candidate = Path(wm) / 'etc' / 'bashrc'
            if candidate.is_file():
                found.append(candidate.resolve())

        home = Path.home()
        patterns = [
            str(home / 'OpenFOAM' / 'OpenFOAM-*' / 'etc' / 'bashrc'),
            str(home / 'OpenFOAM' / 'OpenFOAM-v*' / 'etc' / 'bashrc'),
            '/Applications/OpenFOAM*.app/Contents/Resources/etc/bashrc',
            '/opt/openfoam*/etc/bashrc',
            '/usr/lib/openfoam/openfoam*/etc/bashrc',
            '/Applications/OpenFOAM*/etc/bashrc',
            '/opt/homebrew/opt/openfoam*/etc/bashrc',
            '/usr/local/opt/openfoam*/etc/bashrc',
        ]
        for pattern in patterns:
            for match in sorted(glob.glob(pattern)):
                path = Path(match)
                if not path.is_file():
                    continue
                resolved = path.resolve()
                if resolved not in found:
                    found.append(resolved)

        def sort_key(path: Path) -> tuple[int, str]:
            text = str(path)
            if '.app/' in text:
                return (0, text)
            if text.startswith('/Volumes/'):
                return (2, text)
            return (1, text)

        return sorted(found, key=sort_key)

    def suggested_activation_command(self) -> str:
        paths = self.discover_openfoam_bashrc_paths()
        if not paths:
            return ''
        return f'source {shlex.quote(str(paths[0]))}'

    def openfoam_on_path(self, config: ProjectConfig | None = None) -> bool:
        config = config or ProjectConfig()
        return all(
            shutil.which(command) is not None
            for command in self._configured_stage_commands(config)
        )

    def probe_openfoam(self, config: ProjectConfig) -> OpenFOAMProbe:
        host = self.host_kind()
        bash = self.resolve_bash()
        stage_commands = self._configured_stage_commands(config)
        script_lines = [
            'set -e',
            *self.build_activation_lines(config),
            'set +e',
            'printf "WM_PROJECT_VERSION=%s\\n" "${WM_PROJECT_VERSION:-}"',
            'printf "WM_PROJECT_DIR=%s\\n" "${WM_PROJECT_DIR:-}"',
        ]
        for index, command in enumerate(stage_commands):
            script_lines.append(
                f'printf "STAGE_{index}=%s\\n" "$(command -v {shlex.quote(command)})"'
            )
        command = '\n'.join(script_lines)
        cmd = self.shell_prefix(config, interactive=self.requires_interactive_shell(config)) + [command]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        except FileNotFoundError as exc:
            return OpenFOAMProbe(False, host, bash, '', '', '', f'Interpretador não encontrado: {exc}')
        except subprocess.TimeoutExpired:
            return OpenFOAMProbe(False, host, bash, '', '', '', 'Tempo esgotado ao verificar o ambiente OpenFOAM.')

        stdout = (completed.stdout or '').strip()
        stderr = (completed.stderr or '').strip()
        if completed.returncode != 0:
            if config.activation_enabled:
                detail = f'Falha ao carregar o ambiente OpenFOAM no host {host}.'
            else:
                detail = f'Falha ao executar a verificação do ambiente OpenFOAM no host {host}.'
            if stderr:
                detail += f'\n{stderr}'
            return OpenFOAMProbe(False, host, bash, '', '', '', detail)

        stage_paths: dict[int, str] = {}
        version = ''
        project_dir = ''
        for line in stdout.splitlines():
            if line.startswith('STAGE_'):
                key, value = line.split('=', 1)
                stage_paths[int(key.removeprefix('STAGE_'))] = value.strip()
            elif line.startswith('WM_PROJECT_VERSION='):
                version = line.split('=', 1)[1].strip()
            elif line.startswith('WM_PROJECT_DIR='):
                project_dir = line.split('=', 1)[1].strip()

        missing_commands = [
            command for index, command in enumerate(stage_commands) if not stage_paths.get(index)
        ]
        solver = next((stage_paths[index] for index in range(len(stage_commands)) if stage_paths.get(index)), '')
        ok = not missing_commands
        if ok:
            detail = f'comando(s) de stage encontrado(s): {", ".join(stage_paths.values())}'
            if version:
                detail += f' (OpenFOAM {version})'
        else:
            detail = f'Comando(s) de stage não encontrado(s) no host {host}: {", ".join(missing_commands)}.'
            if stderr:
                detail += f'\n{stderr}'

        return OpenFOAMProbe(ok, host, bash, solver, project_dir, version, detail)

    def _configured_stage_commands(self, config: ProjectConfig) -> list[str]:
        raw_commands = config.internal_stage_commands
        if isinstance(raw_commands, str):
            raw_commands = raw_commands.splitlines()

        commands: list[str] = []
        for raw_command in raw_commands or ['foamRun']:
            tokens = shlex.split(str(raw_command).strip())
            if tokens and tokens[0] not in commands:
                commands.append(tokens[0])
        return commands or ['foamRun']

    def sanitize_label(self, text: str) -> str:
        cleaned = ''.join(ch if ch.isalnum() or ch in {'_', '-'} else '_' for ch in text.strip())
        cleaned = cleaned.strip('_')
        return cleaned or 'command'

    def _uses_login_shell(self) -> bool:
        return self.host_kind() in {'wsl', 'windows'}
