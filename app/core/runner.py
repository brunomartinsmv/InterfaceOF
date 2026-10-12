from __future__ import annotations

import os
import signal
import shlex
import subprocess
import threading
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
        self._lock = threading.Lock()
        self._interrupted: bool = False

    @property
    def is_interrupted(self) -> bool:
        with self._lock:
            return self._interrupted

    def reset_interrupted(self) -> None:
        with self._lock:
            self._interrupted = False

    def _kill_process_tree(self, proc: subprocess.Popen[str], force: bool = False) -> None:
        if proc.poll() is not None:
            return
        pid = proc.pid
        if os.name != 'nt':
            sig = signal.SIGKILL if force else signal.SIGTERM
            try:
                os.killpg(pid, sig)
                return
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            if force:
                proc.kill()
            else:
                proc.terminate()
        except OSError:
            pass

    def run_command_sequence(
        self,
        case_dir: Path,
        command_sequence: list[dict[str, str]],
        config: ProjectConfig,
        case_name: str,
        start_index: int = 1,
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

        for i, entry in enumerate(command_sequence):
            idx = start_index + i
            if self.is_interrupted:
                status.status = 'interrupted'
                status.error_type = 'interrupted'
                status.error_message = 'Execução cancelada pelo usuário.'
                break

            phase = entry.get('phase', 'run')
            command = entry['command'].strip()
            stage_label = entry.get('stage_label')
            label = entry.get('label') or command.split()[0]
            safe_label = self.environment.sanitize_label(label)
            safe_stage = f'_{self.environment.sanitize_label(stage_label)}' if stage_label else ''
            log_name = f'{idx:03d}_{phase}{safe_stage}_{safe_label}.log'
            script_name = f'{idx:03d}_{phase}{safe_stage}_{safe_label}.sh'
            log_path = logs_dir / log_name
            script_path = scripts_dir / script_name

            script_lines = ['#!/usr/bin/env bash', 'set -o pipefail', 'set -e']
            script_lines.extend(self.environment.build_activation_lines(config))
            script_lines.append(command)
            write_text(script_path, '\n'.join(script_lines) + '\n')
            script_path.chmod(0o755)

            interactive = self.environment.requires_interactive_shell(config)
            inner_bash = 'bash' if not self.environment.is_native_unix() else shlex.quote(self.environment.resolve_bash())
            shell_command = f'{inner_bash} {self.environment.quote_path(script_path)}'
            cmd = self.environment.shell_prefix(config, interactive=interactive) + [shell_command]

            started_at = datetime.now()
            if command_started_callback:
                command_started_callback(label, str(log_path))
            if stdout_callback:
                stdout_callback(f'\n===== [{case_name}] {phase}:{label} -> {log_path.name} =====\n')

            popen_kwargs: dict[str, object] = {
                'cwd': str(case_dir),
                'stdout': subprocess.PIPE,
                'stderr': subprocess.STDOUT,
                'text': True,
                'bufsize': 1,
            }
            if os.name != 'nt':
                popen_kwargs['start_new_session'] = True

            with self._lock:
                if self._interrupted:
                    status.status = 'interrupted'
                    status.error_type = 'interrupted'
                    status.error_message = 'Execução cancelada pelo usuário.'
                    break
                self._process = subprocess.Popen(cmd, **popen_kwargs)

            proc = self._process
            assert proc.stdout is not None
            try:
                with log_path.open('w', encoding='utf-8') as log_file:
                    for line in proc.stdout:
                        clean_line = line.rstrip('\n')
                        if len(lines) < 2000:
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
                            if not status.error_type:
                                status.error_type = 'solver_error'
                                status.error_message = log_event.error_message
                        residual = self.residual_parser.parse_line(line)
                        if residual and residual_callback:
                            residual_callback(residual.equation, residual.initial_residual, str(log_path), current_time)

                return_code = proc.wait()
            except Exception as exc:
                self._kill_process_tree(proc, force=False)
                try:
                    proc.wait(timeout=2.0)
                except (subprocess.TimeoutExpired, Exception):
                    self._kill_process_tree(proc, force=True)
                    try:
                        proc.wait(timeout=1.0)
                    except Exception:
                        pass
                if not status.error_type:
                    status.error_type = 'runner_exception'
                    status.error_message = f'Erro durante execução do comando: {exc}'
                raise
            finally:
                with self._lock:
                    if self._process is proc:
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

            if self.is_interrupted:
                status.status = 'interrupted'
                status.error_type = 'interrupted'
                status.error_message = 'Execução cancelada pelo usuário.'
                overall_return = return_code
                break

            if return_code != 0:
                overall_return = return_code
                if not status.error_type:
                    status.error_type = 'command_failed'
                    status.error_message = f'Comando falhou ({return_code}): {command}'
                break

        status.end_time = datetime.now()
        if self.is_interrupted:
            status.status = 'interrupted'
            status.error_type = 'interrupted'
            status.error_message = 'Execução cancelada pelo usuário.'
        elif overall_return != 0 or status.error_type is not None:
            if not status.error_type:
                status.error_type = 'command_failed'
                status.error_message = status.error_message or 'Um ou mais comandos retornaram código diferente de zero.'
            status.status = 'error'
        else:
            status.status = 'completed'

        status.metrics['wall_clock_seconds'] = (status.end_time - status.start_time).total_seconds()
        status.metrics['return_code'] = overall_return
        status.metrics['command_logs'] = [record.log_path for record in command_records]
        if status_callback:
            status_callback(status)
        return RunnerResult(return_code=overall_return, status=status, raw_log_lines=lines, command_records=command_records)

    def stop_case(self, wait_timeout: float = 3.0) -> None:
        with self._lock:
            self._interrupted = True
            proc = self._process
            if proc is None or proc.poll() is not None:
                return
            self._kill_process_tree(proc, force=False)

        try:
            proc.wait(timeout=wait_timeout)
        except (subprocess.TimeoutExpired, Exception):
            self._kill_process_tree(proc, force=True)
            try:
                proc.wait(timeout=1.0)
            except Exception:
                pass
