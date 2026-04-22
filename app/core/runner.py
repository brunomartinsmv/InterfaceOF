from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.core.environment_adapter import EnvironmentAdapter
from app.core.log_parser import LogParser
from app.core.residual_parser import ResidualParser
from app.models.project_config import ProjectConfig
from app.models.run_status import RunStatus
from app.utils.file_ops import ensure_dir, write_text

StdoutCallback = Callable[[str], None]
ResidualCallback = Callable[[str, float, str, float | None], None]
StatusCallback = Callable[[RunStatus], None]
TimeCallback = Callable[[float | None], None]
CommandStartedCallback = Callable[[str, str], None]


@dataclass(slots=True)
class CommandExecutionRecord:
    phase: str
    command: str
    stage_label: str | None
    log_path: str
    script_path: str
    return_code: int
    started_at: str
    ended_at: str


@dataclass(slots=True)
class RunnerResult:
    return_code: int
    status: RunStatus
    raw_log_lines: list[str] = field(default_factory=list)
    command_records: list[CommandExecutionRecord] = field(default_factory=list)


class Runner:
    def __init__(self, environment: EnvironmentAdapter | None = None) -> None:
        self.log_parser = LogParser()
        self.residual_parser = ResidualParser()
        self.environment = environment or EnvironmentAdapter()
        self._process: subprocess.Popen[str] | None = None

    def run_command_sequence(
        self,
        case_dir: Path,
        command_sequence: list[dict[str, str]],
        config: ProjectConfig,
        case_name: str,
        stdout_callback: StdoutCallback | None = None,
        residual_callback: ResidualCallback | None = None,
        status_callback: StatusCallback | None = None,
        time_callback: TimeCallback | None = None,
        command_started_callback: CommandStartedCallback | None = None,
    ) -> RunnerResult:
        status = RunStatus(case_name=case_name, status='running', start_time=datetime.now())
        current_time: float | None = None
        status.metrics['activation_enabled'] = config.activation_enabled
        status.metrics['activation_mode'] = config.activation_mode
        status.metrics['activation_command'] = config.activation_command if config.activation_enabled else ''
        status.metrics['log_error_messages'] = []
        if status_callback:
            status_callback(status)

        logs_dir = ensure_dir(case_dir / 'logs')
        scripts_dir = ensure_dir(case_dir / '.of_campaign_scripts')
        lines: list[str] = []
        command_records: list[CommandExecutionRecord] = []
        overall_return = 0

        for idx, entry in enumerate(command_sequence, start=1):
            phase = entry.get('phase', 'run')
            command = entry['command'].strip()
            stage_label = entry.get('stage_label')
            label = entry.get('label') or command.split()[0]
            safe_label = self.environment.sanitize_label(label)
            log_name = f'{idx:03d}_{phase}_{safe_label}.log'
            script_name = f'{idx:03d}_{phase}_{safe_label}.sh'
            log_path = logs_dir / log_name
            script_path = scripts_dir / script_name

            script_lines = ['#!/usr/bin/env bash', 'set -o pipefail']
            if command.strip().startswith('source '):
                script_lines.append('set -e')
            else:
                script_lines.append('set -e')
            script_lines.extend(self.environment.build_activation_lines(config))
            script_lines.append(command)
            write_text(script_path, '\n'.join(script_lines) + '\n')
            script_path.chmod(0o755)

            interactive = self.environment.requires_interactive_shell(config)
            shell_command = f'bash {self.environment.quote_path(script_path)}'
            cmd = self.environment.shell_prefix(config, interactive=interactive) + [shell_command]

            started_at = datetime.now()
            if command_started_callback:
                command_started_callback(label, str(log_path))
            if stdout_callback:
                stdout_callback(f'\n===== [{case_name}] {phase}:{label} -> {log_path.name} =====\n')

            self._process = subprocess.Popen(
                cmd,
                cwd=str(case_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            assert self._process.stdout is not None
            with log_path.open('w', encoding='utf-8') as log_file:
                for line in self._process.stdout:
                    clean_line = line.rstrip('\n')
                    lines.append(clean_line)
                    log_file.write(line)
                    log_file.flush()
                    if stdout_callback:
                        stdout_callback(line)
                    log_event = self.log_parser.parse_line(line)
                    if log_event.current_time is not None:
                        current_time = log_event.current_time
                        status.last_simulated_time = log_event.current_time
                        if time_callback:
                            time_callback(log_event.current_time)
                    if log_event.error_detected:
                        status.metrics.setdefault('log_error_messages', []).append(log_event.error_message)
                    residual = self.residual_parser.parse_line(line)
                    if residual and residual_callback:
                        residual_callback(residual.equation, residual.initial_residual, str(log_path), current_time)

            return_code = self._process.wait()
            self._process = None
            ended_at = datetime.now()
            command_records.append(
                CommandExecutionRecord(
                    phase=phase,
                    command=command,
                    stage_label=stage_label,
                    log_path=str(log_path),
                    script_path=str(script_path),
                    return_code=return_code,
                    started_at=started_at.isoformat(),
                    ended_at=ended_at.isoformat(),
                )
            )
            if return_code != 0:
                overall_return = return_code
                if not status.error_type:
                    status.error_type = 'command_failed'
                    status.error_message = f'Comando falhou ({return_code}): {command}'
                break

        status.end_time = datetime.now()
        if overall_return != 0:
            if not status.error_type:
                status.error_type = 'command_failed'
                status.error_message = status.error_message or 'Um ou mais comandos retornaram código diferente de zero.'
            status.status = 'error'
        else:
            status.status = 'completed'
            # Mensagens detectadas no log são mantidas como diagnóstico, mas não classificam o caso como erro
            # quando todos os comandos terminam com código 0.
            if status.error_type == 'solver_error':
                status.metrics['log_error_messages'] = status.metrics.get('log_error_messages', [])
                status.error_type = None
                status.error_message = None
        status.metrics['wall_clock_seconds'] = (status.end_time - status.start_time).total_seconds()
        status.metrics['return_code'] = overall_return
        status.metrics['command_logs'] = [record.log_path for record in command_records]
        if status_callback:
            status_callback(status)
        return RunnerResult(return_code=overall_return, status=status, raw_log_lines=lines, command_records=command_records)

    def stop_case(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
