from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.case_builder import CaseBuilder
from app.core.metadata_writer import MetadataWriter
from app.core.parameter_loader import LoadedParameters, ParameterLoader
from app.core.paraview_launcher import ParaViewLauncher
from app.core.preflight_validator import PreflightReport, PreflightValidator
from app.core.runner import Runner
from app.core.scheduler import Scheduler
from app.core.summary_writer import SummaryWriter
from app.core.template_engine import TemplateEngine
from app.models.project_config import ProjectConfig
from app.models.run_status import RunStatus
from app.utils.file_ops import ensure_dir, write_json
from app.utils.paths import build_campaign_paths


def read_controldict_endtime(case_dir: Path) -> float | None:
    """Lê o endTime ativo de system/controlDict sem interpretar comentários."""
    control_dict = case_dir / 'system' / 'controlDict'
    if not control_dict.is_file():
        return None
    try:
        content = control_dict.read_text(encoding='utf-8')
    except OSError:
        return None
    comment_re = re.compile(r'(/\*.*?\*/|//[^\n]*)', flags=re.DOTALL)

    def _mask_comment(m: re.Match) -> str:
        return ''.join('\n' if c == '\n' else ' ' for c in m.group(0))

    clean = comment_re.sub(_mask_comment, content)
    match = re.search(r'(?m)^\s*endTime\b\s*([^;]+);', clean)
    if match:
        try:
            return float(match.group(1).strip())
        except ValueError:
            return None
    return None


def update_controldict_for_stage(case_dir: Path, target_time: float, start_from_latest: bool = True) -> bool:
    """Ajusta endTime, stopAt e startFrom em system/controlDict sem alterar comentários."""
    control_dict = case_dir / 'system' / 'controlDict'
    if not control_dict.is_file():
        return False
    try:
        content = control_dict.read_text(encoding='utf-8')
    except OSError:
        return False

    comment_re = re.compile(r'(/\*.*?\*/|//[^\n]*)', flags=re.DOTALL)

    def _mask_comment(m: re.Match) -> str:
        return ''.join('\n' if c == '\n' else ' ' for c in m.group(0))

    masked = comment_re.sub(_mask_comment, content)

    replacements: list[tuple[int, int, str]] = []

    m_end = re.search(r'(?m)^\s*endTime\b[^;]*;', masked)
    if m_end:
        replacements.append((m_end.start(), m_end.end(), f'endTime         {target_time};'))

    m_stop = re.search(r'(?m)^\s*stopAt\b[^;]*;', masked)
    if m_stop:
        replacements.append((m_stop.start(), m_stop.end(), 'stopAt          endTime;'))

    m_start = re.search(r'(?m)^\s*startFrom\b[^;]*;', masked)
    if start_from_latest and m_start:
        replacements.append((m_start.start(), m_start.end(), 'startFrom       latestTime;'))

    replacements.sort(key=lambda r: r[0], reverse=True)
    res = content
    for start, end, new_text in replacements:
        res = res[:start] + new_text + res[end:]

    extra_lines: list[str] = []
    if not m_end:
        extra_lines.append(f'endTime         {target_time};')
    if not m_stop:
        extra_lines.append('stopAt          endTime;')
    if start_from_latest and not m_start:
        extra_lines.append('startFrom       latestTime;')

    if extra_lines:
        res += '\n' + '\n'.join(extra_lines) + '\n'

    try:
        control_dict.write_text(res, encoding='utf-8')
        return True
    except OSError:
        return False


def detect_latest_time(case_dir: Path) -> float | None:
    """Detecta o maior tempo gravado inspecionando a raiz e diretórios processor*."""
    times: list[float] = []
    if not case_dir.is_dir():
        return None

    def _scan_dir(dir_path: Path) -> None:
        try:
            for item in dir_path.iterdir():
                if item.is_dir():
                    try:
                        times.append(float(item.name))
                    except ValueError:
                        pass
        except OSError:
            pass

    _scan_dir(case_dir)
    try:
        for proc_dir in case_dir.glob('processor*'):
            if proc_dir.is_dir():
                _scan_dir(proc_dir)
    except OSError:
        pass

    return max(times) if times else None


def _replace_solver_in_command(cmd: str, solver_override: str) -> str:
    tokens = cmd.split()
    if not tokens:
        return solver_override

    wrappers = {'mpirun', 'mpiexec', 'srun', 'runApplication', 'runParallel', 'time', 'env'}
    wrapper_flags_with_val = {
        '-np', '-n', '-N', '-c', '--nprocs', '-nprocs',
        '-x', '-env', '--env',
        '--bind-to', '--map-by', '--rank-by',
        '-hostfile', '--hostfile', '-machinefile', '--machinefile',
        '-H', '-host', '--host',
        '-wd', '-wdir', '-path',
    }

    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if '=' in tok and not tok.startswith('-'):
            idx += 1
        elif Path(tok).name in wrappers or tok in wrappers:
            idx += 1
        elif '=' in tok and tok.startswith('-'):
            idx += 1
        elif tok in {'--mca', '-mca'}:
            idx += 3
        elif tok in wrapper_flags_with_val:
            idx += 2
        elif tok.startswith('-'):
            idx += 1
        else:
            tokens[idx] = solver_override
            return ' '.join(tokens)

    tokens.append(solver_override)
    return ' '.join(tokens)


class CampaignManager:
    def __init__(self) -> None:
        self.parameter_loader = ParameterLoader()
        self.validator = PreflightValidator()
        self.case_builder = CaseBuilder()
        self.scheduler = Scheduler()
        self.runner = Runner()
        self.metadata_writer = MetadataWriter()
        self.summary_writer = SummaryWriter()
        self.template_engine = TemplateEngine()
        self.paraview_launcher = ParaViewLauncher()
        self.last_campaign_dir: Path | None = None
        self.loaded_parameters: LoadedParameters | None = None
        self.preflight_report: PreflightReport | None = None
        self.statuses: list[RunStatus] = []

    def stop(self) -> None:
        self.runner.stop_case()

    def reset_stop(self) -> None:
        self.runner.reset_interrupted()

    def validate_project(self, config: ProjectConfig) -> PreflightReport:
        if not config.base_case_dir or not config.primary_csv:
            raise ValueError('Configuração incompleta para validação.')
        loaded = self.parameter_loader.load(config.primary_csv, config.secondary_csv)
        report = self.validator.validate(config.base_case_dir, loaded)
        self.loaded_parameters = loaded
        self.preflight_report = report
        return report

    def run_campaign(
        self,
        config: ProjectConfig,
        stdout_callback=None,
        residual_callback=None,
        status_callback=None,
        time_callback=None,
        command_started_callback=None,
    ) -> Path:
        self.validate_project(config)
        assert self.loaded_parameters is not None
        assert self.preflight_report is not None
        if not self.preflight_report.ok:
            raise ValueError('Projeto inválido. Corrija os erros antes de executar.')
        if not config.output_dir or not config.base_case_dir:
            raise ValueError('Configuração incompleta para execução.')

        campaign_paths = build_campaign_paths(config.output_dir)
        ensure_dir(campaign_paths.campaign_dir)
        ensure_dir(campaign_paths.logs_dir)
        write_json(campaign_paths.config_json, config.to_dict())

        self.statuses = []
        self.last_campaign_dir = campaign_paths.campaign_dir
        changes_total = 0
        residual_points_total = 0
        stages_total = 0

        for case in self.loaded_parameters.cases:
            if self.runner.is_interrupted:
                break

            case_start_time = datetime.now()
            case_status = RunStatus(
                case_name=case.case_name,
                status='running',
                start_time=case_start_time,
            )
            runner_mode = case.config_parameters.get('cfg__runner_mode', config.runner_mode)
            if runner_mode == 'allrun' and case.stages:
                raise ValueError(
                    f"Caso {case.case_name!r}: modo 'allrun' não é compatível com simulação multiestágio. Utilize o modo 'internal'."
                )

            case_status.metrics['activation_enabled'] = config.activation_enabled
            case_status.metrics['activation_mode'] = config.activation_mode
            case_status.metrics['activation_command'] = config.activation_command if config.activation_enabled else ''

            solver_override = case.config_parameters.get('cfg__solver')
            if solver_override:
                resolved_solver = str(solver_override).strip()
            elif config.default_solver:
                resolved_solver = str(config.default_solver).strip()
            elif config.internal_stage_commands:
                resolved_solver = config.internal_stage_commands[0].split()[0]
            else:
                resolved_solver = 'foamRun'

            case_status.metrics['solver'] = resolved_solver
            case_status.metrics['n_processors'] = str(case.config_parameters.get('cfg__n_processors', config.n_processors))
            case_status.metrics['runner_mode'] = runner_mode
            case_status.metrics['n_stages'] = len(case.stages)

            if status_callback:
                status_callback(case_status)

            built = self.case_builder.build(config.base_case_dir, campaign_paths.campaign_dir, case)
            case.output_dir = built.case_dir
            foam_file = self.paraview_launcher.ensure_case_foam(built.case_dir, case.case_name)
            current_parameters = dict(case.template_parameters)
            changes_log = [f'[initial] arquivos alterados: {path}' for path in built.replacement_summary.files_touched]
            case_substitutions = built.replacement_summary.replaced_count

            if built.replacement_summary.remaining_markers:
                case_status.status = 'error'
                case_status.error_type = 'missing_markers'
                case_status.error_message = (
                    f'Marcadores remanescentes no caso {case.case_name!r}: {built.replacement_summary.remaining_markers}'
                )
                case_status.end_time = datetime.now()
                self.statuses.append(case_status)
                if status_callback:
                    status_callback(case_status)
                break

            residual_points_case: list[dict[str, Any]] = []
            command_manifest: list[dict[str, Any]] = []

            def _residual_cb(eq: str, val: float, source_log: str, time_value: float | None) -> None:
                nonlocal residual_points_case
                residual_points_case.append({'equation': eq, 'initial_residual': val, 'source_log': source_log, 'time': time_value})
                if residual_callback:
                    residual_callback(eq, val, source_log, time_value)

            command_sequence = self._build_command_sequence(case, config, case_dir=built.case_dir)
            if command_sequence:
                result = self.runner.run_command_sequence(
                    case_dir=built.case_dir,
                    command_sequence=command_sequence,
                    config=config,
                    case_name=case.case_name,
                    start_index=len(command_manifest) + 1,
                    stdout_callback=stdout_callback,
                    residual_callback=_residual_cb,
                    status_callback=status_callback,
                    time_callback=time_callback,
                    command_started_callback=command_started_callback,
                )
                command_manifest.extend([self.metadata_writer.to_serializable(record) for record in result.command_records])
                if result.status.status != 'completed':
                    case_status.status = result.status.status
                    case_status.error_type = result.status.error_type
                    case_status.error_message = result.status.error_message
                if result.status.last_simulated_time is not None:
                    case_status.last_simulated_time = max(case_status.last_simulated_time or 0.0, result.status.last_simulated_time)

            executed_stages_count = 0
            if case_status.status == 'running' and not self.runner.is_interrupted and case.stages:
                stage_status, executed_stages_count, stage_substitutions = self._run_stages(
                    case=case,
                    case_dir=built.case_dir,
                    current_parameters=current_parameters,
                    config=config,
                    stdout_callback=stdout_callback,
                    residual_callback=_residual_cb,
                    status_callback=status_callback,
                    time_callback=time_callback,
                    command_started_callback=command_started_callback,
                    changes_log=changes_log,
                    command_manifest=command_manifest,
                )
                case_substitutions += stage_substitutions
                if stage_status is not None and stage_status.status != 'completed':
                    case_status.status = stage_status.status
                    case_status.error_type = stage_status.error_type
                    case_status.error_message = stage_status.error_message
                if stage_status is not None and stage_status.last_simulated_time is not None:
                    case_status.last_simulated_time = max(case_status.last_simulated_time or 0.0, stage_status.last_simulated_time)

            if case_status.status == 'running' and not self.runner.is_interrupted and runner_mode != 'allrun':
                post_sequence = self._build_post_sequence(case, config)
                if post_sequence:
                    post_result = self.runner.run_command_sequence(
                        case_dir=built.case_dir,
                        command_sequence=post_sequence,
                        config=config,
                        case_name=case.case_name,
                        start_index=len(command_manifest) + 1,
                        stdout_callback=stdout_callback,
                        residual_callback=_residual_cb,
                        status_callback=status_callback,
                        time_callback=time_callback,
                        command_started_callback=command_started_callback,
                    )
                    command_manifest.extend([self.metadata_writer.to_serializable(record) for record in post_result.command_records])
                    if post_result.status.status != 'completed':
                        case_status.status = post_result.status.status
                        case_status.error_type = post_result.status.error_type
                        case_status.error_message = post_result.status.error_message

            latest_detected = detect_latest_time(built.case_dir)
            if latest_detected is not None:
                case_status.last_simulated_time = max(case_status.last_simulated_time or 0.0, latest_detected)

            case_status.end_time = datetime.now()
            if self.runner.is_interrupted:
                case_status.status = 'interrupted'
                case_status.error_type = 'interrupted'
                case_status.error_message = 'Execução cancelada pelo usuário.'
            elif case_status.status == 'running':
                case_status.status = 'completed'

            case_status.metrics['wall_clock_seconds'] = (case_status.end_time - case_status.start_time).total_seconds()
            case_status.metrics['executed_stages'] = executed_stages_count
            case_status.metrics['n_changes'] = case_substitutions
            case_status.metrics['n_residual_points'] = len(residual_points_case)
            case_status.metrics['case_dir'] = str(built.case_dir)
            case_status.metrics['foam_file'] = str(foam_file)
            case_status.metrics['command_logs'] = [record['log_path'] for record in command_manifest]
            self.statuses.append(case_status)

            self.metadata_writer.write_case_metadata(built.case_dir, {
                'case_name': case.case_name,
                'timestamp': datetime.now().isoformat(),
                'template_parameters': case.template_parameters,
                'config_parameters': case.config_parameters,
                'stages': [
                    {
                        'target_time': stage.target_time,
                        'stage_label': stage.stage_label,
                        'changes': [{'parameter': c.parameter, 'value': c.value} for c in stage.changes],
                    }
                    for stage in case.stages
                ],
            })
            self.metadata_writer.write_case_log(built.case_dir, self.metadata_writer.serialize_status(case_status))
            self.metadata_writer.write_changes_log(built.case_dir, changes_log)
            self.metadata_writer.write_command_manifest(built.case_dir, {'commands': command_manifest})

            changes_total += case_substitutions
            residual_points_total += len(residual_points_case)
            stages_total += executed_stages_count

            if residual_points_case:
                pd.DataFrame(residual_points_case).to_csv(built.case_dir / 'residuals.csv', index=False)

            if self.runner.is_interrupted or case_status.status == 'interrupted':
                break

        self.summary_writer.write_campaign_summary(campaign_paths.summary_csv, self.statuses)
        campaign_name = campaign_paths.campaign_dir.name
        metrics = self._compute_campaign_metrics(changes_total, residual_points_total, stages_total)
        self.summary_writer.write_campaign_metrics(campaign_paths.metrics_json, metrics)
        self.metadata_writer.write_campaign_metadata(campaign_paths.campaign_dir, metrics, campaign_name)
        return campaign_paths.campaign_dir

    def _run_stages(
        self,
        *,
        case,
        case_dir: Path,
        current_parameters: dict[str, str],
        config: ProjectConfig,
        stdout_callback,
        residual_callback,
        status_callback,
        time_callback,
        command_started_callback,
        changes_log: list[str],
        command_manifest: list[dict[str, Any]],
    ) -> tuple[RunStatus | None, int, int]:
        if not case.stages:
            return None, 0, 0

        stages = sorted(case.stages, key=lambda s: s.target_time)
        status: RunStatus | None = None
        executed_stages = 0
        total_substitutions = 0

        # Obter o endTime final pretendido (seja de template_parameters['end_time'] ou do controlDict inicial)
        final_target = read_controldict_endtime(case_dir)
        if 'end_time' in case.template_parameters:
            try:
                final_target = float(case.template_parameters['end_time'])
            except (ValueError, TypeError):
                pass

        # Intervalo inicial: executa com parâmetros iniciais até stages[0].target_time
        initial_target = stages[0].target_time
        if not update_controldict_for_stage(case_dir, target_time=initial_target, start_from_latest=False):
            raise ValueError(f'Falha ao configurar controlDict para tempo inicial {initial_target}')

        initial_stage_cmds = self._build_stage_command_sequence(case, config, stage_label=f'initial_to_{initial_target}')
        initial_res = self.runner.run_command_sequence(
            case_dir=case_dir,
            command_sequence=initial_stage_cmds,
            config=config,
            case_name=case.case_name,
            start_index=len(command_manifest) + 1,
            stdout_callback=stdout_callback,
            residual_callback=residual_callback,
            status_callback=status_callback,
            time_callback=time_callback,
            command_started_callback=command_started_callback,
        )
        command_manifest.extend([self.metadata_writer.to_serializable(r) for r in initial_res.command_records])
        status = initial_res.status
        if status.status in {'error', 'interrupted'} or self.runner.is_interrupted:
            return status, executed_stages, total_substitutions

        for idx, stage in enumerate(stages):
            if self.runner.is_interrupted:
                break

            for change in stage.changes:
                current_parameters[change.parameter] = change.value
                changes_log.append(f'[{stage.stage_label}] {change.parameter} -> {change.value} @ {stage.target_time}')

            summary = self.template_engine.apply_parameters(case_dir, current_parameters)
            total_substitutions += summary.replaced_count
            changes_log.extend(f'[{stage.stage_label}] arquivo alterado: {path}' for path in summary.files_touched)
            if summary.remaining_markers:
                raise ValueError(
                    f'Marcadores remanescentes após {stage.stage_label} em {case.case_name}: {summary.remaining_markers}'
                )

            if idx + 1 < len(stages):
                next_target = stages[idx + 1].target_time
            else:
                target_cand = final_target
                if 'end_time' in current_parameters:
                    try:
                        target_cand = float(current_parameters['end_time'])
                    except (ValueError, TypeError):
                        pass
                next_target = target_cand if (target_cand is not None and target_cand > stage.target_time) else None

            if next_target is not None and next_target > stage.target_time:
                if not update_controldict_for_stage(case_dir, target_time=next_target, start_from_latest=True):
                    raise ValueError(f'Falha ao configurar controlDict para {stage.stage_label} (target {next_target})')

                cmd_seq = self._build_stage_command_sequence(case, config, stage_label=stage.stage_label)
                stage_res = self.runner.run_command_sequence(
                    case_dir=case_dir,
                    command_sequence=cmd_seq,
                    config=config,
                    case_name=case.case_name,
                    start_index=len(command_manifest) + 1,
                    stdout_callback=stdout_callback,
                    residual_callback=residual_callback,
                    status_callback=status_callback,
                    time_callback=time_callback,
                    command_started_callback=command_started_callback,
                )
                command_manifest.extend([self.metadata_writer.to_serializable(r) for r in stage_res.command_records])
                status = stage_res.status
                executed_stages += 1
                if status.status in {'error', 'interrupted'} or self.runner.is_interrupted:
                    break
            else:
                executed_stages += 1

        return status, executed_stages, total_substitutions

    def _build_command_sequence(self, case, config: ProjectConfig, case_dir: Path | None = None) -> list[dict[str, str]]:
        runner_mode = case.config_parameters.get('cfg__runner_mode', config.runner_mode)
        if runner_mode == 'allrun':
            return [{'phase': 'run', 'label': 'Allrun', 'command': './Allrun', 'stage_label': 'allrun'}]

        sequence: list[dict[str, str]] = []
        for command in self._parse_commands(config.internal_setup_commands):
            sequence.append({'phase': 'setup', 'label': command.split()[0], 'command': command})
        if not case.stages:
            for command in self._stage_commands(case, config):
                sequence.append({'phase': 'run', 'label': command.split()[0], 'command': command, 'stage_label': 'main'})
        return sequence

    def _build_post_sequence(self, case, config: ProjectConfig) -> list[dict[str, str]]:
        runner_mode = case.config_parameters.get('cfg__runner_mode', config.runner_mode)
        if runner_mode == 'allrun':
            return []
        return [
            {'phase': 'post', 'label': command.split()[0], 'command': command}
            for command in self._parse_commands(config.internal_post_commands)
        ]

    def _build_stage_command_sequence(self, case, config: ProjectConfig, *, stage_label: str) -> list[dict[str, str]]:
        return [
            {'phase': 'stage', 'label': command.split()[0], 'command': command, 'stage_label': stage_label}
            for command in self._stage_commands(case, config)
        ]

    def _stage_commands(self, case, config: ProjectConfig) -> list[str]:
        commands = self._parse_commands(config.internal_stage_commands)
        if case and 'cfg__solver' in case.config_parameters:
            solver_override = str(case.config_parameters['cfg__solver']).strip()
            if solver_override:
                if not commands:
                    return [solver_override]
                known_solvers = {'foamRun', 'simpleFoam', 'pimpleFoam', 'interFoam', 'icoFoam', 'rhoPimpleFoam', 'buoyantPimpleFoam'}
                aux_tools = {'blockMesh', 'checkMesh', 'decomposePar', 'reconstructPar', 'setFields', 'snappyHexMesh'}

                updated: list[str] = []
                replaced = False
                for cmd in commands:
                    if not replaced and any(tok in known_solvers for tok in cmd.split()):
                        updated.append(_replace_solver_in_command(cmd, solver_override))
                        replaced = True
                    else:
                        updated.append(cmd)

                if replaced:
                    return updated

                updated = []
                for cmd in commands:
                    tokens = cmd.split()
                    if not replaced and tokens and tokens[0] not in aux_tools:
                        updated.append(_replace_solver_in_command(cmd, solver_override))
                        replaced = True
                    else:
                        updated.append(cmd)

                if replaced:
                    return updated

                return commands + [solver_override]
        return commands if commands else ['foamRun']

    def _parse_commands(self, commands: list[str] | str) -> list[str]:
        if isinstance(commands, str):
            lines = commands.splitlines()
        else:
            lines = commands
        parsed = [str(line).strip() for line in lines if str(line).strip()]
        return parsed

    def _compute_campaign_metrics(self, changes_total: int, residual_points_total: int, stages_total: int) -> dict[str, Any]:
        total_cases = len(self.loaded_parameters.cases) if self.loaded_parameters else len(self.statuses)
        completed = sum(1 for s in self.statuses if s.status == 'completed')
        errors = sum(1 for s in self.statuses if s.status == 'error')
        interrupted = sum(1 for s in self.statuses if s.status == 'interrupted')
        wall_times = [float(s.metrics.get('wall_clock_seconds', 0.0)) for s in self.statuses]
        planned_stages = sum(len(c.stages) for c in self.loaded_parameters.cases) if self.loaded_parameters else stages_total
        executed_cases_count = len(self.statuses)

        return {
            'total_cases': total_cases,
            'completed_cases': completed,
            'error_cases': errors,
            'interrupted_cases': interrupted,
            'campaign_wall_clock_seconds_total': sum(wall_times),
            'campaign_wall_clock_seconds_mean': (sum(wall_times) / executed_cases_count) if executed_cases_count else 0.0,
            'total_stages': planned_stages,
            'total_executed_stages': stages_total,
            'total_changes': changes_total,
            'total_markers_found': len(self.preflight_report.markers) if self.preflight_report else 0,
            'total_markers_substituted': changes_total,
            'total_residual_points': residual_points_total,
        }
