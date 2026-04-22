from __future__ import annotations

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
        if self.loaded_parameters is None or self.preflight_report is None:
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
            built = self.case_builder.build(config.base_case_dir, campaign_paths.campaign_dir, case)
            case.output_dir = built.case_dir
            foam_file = self.paraview_launcher.ensure_case_foam(built.case_dir, case.case_name)
            current_parameters = dict(case.template_parameters)
            changes_log = [f'[initial] arquivos alterados: {path}' for path in built.replacement_summary.files_touched]
            residual_points_case: list[dict[str, Any]] = []
            command_manifest: list[dict[str, Any]] = []

            def _residual_cb(eq: str, val: float, source_log: str, time_value: float | None) -> None:
                nonlocal residual_points_case
                residual_points_case.append({'equation': eq, 'initial_residual': val, 'source_log': source_log, 'time': time_value})
                if residual_callback:
                    residual_callback(eq, val, source_log, time_value)

            command_sequence = self._build_command_sequence(case, config)
            if command_sequence:
                result = self.runner.run_command_sequence(
                    case_dir=built.case_dir,
                    command_sequence=command_sequence,
                    config=config,
                    case_name=case.case_name,
                    stdout_callback=stdout_callback,
                    residual_callback=_residual_cb,
                    status_callback=status_callback,
                    time_callback=time_callback,
                    command_started_callback=command_started_callback,
                )
                command_manifest.extend([self.metadata_writer.to_serializable(record) for record in result.command_records])
                status = result.status
            else:
                status = RunStatus(case_name=case.case_name, status='completed', start_time=datetime.now(), end_time=datetime.now())

            if status.status != 'error':
                stage_status = self._run_stages(
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
                if stage_status is not None:
                    status = stage_status

            if status.status != 'error':
                post_sequence = self._build_post_sequence(case, config)
                if post_sequence:
                    post_result = self.runner.run_command_sequence(
                        case_dir=built.case_dir,
                        command_sequence=post_sequence,
                        config=config,
                        case_name=case.case_name,
                        stdout_callback=stdout_callback,
                        residual_callback=_residual_cb,
                        status_callback=status_callback,
                        time_callback=time_callback,
                        command_started_callback=command_started_callback,
                    )
                    command_manifest.extend([self.metadata_writer.to_serializable(record) for record in post_result.command_records])
                    status = post_result.status

            status.metrics['n_stages'] = len(case.stages)
            status.metrics['n_changes'] = built.replacement_summary.replaced_count + max(0, len(changes_log) - 1)
            status.metrics['n_residual_points'] = len(residual_points_case)
            status.metrics['case_dir'] = str(built.case_dir)
            status.metrics['foam_file'] = str(foam_file)
            self.statuses.append(status)

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
            self.metadata_writer.write_case_log(built.case_dir, self.metadata_writer.serialize_status(status))
            self.metadata_writer.write_changes_log(built.case_dir, changes_log)
            self.metadata_writer.write_command_manifest(built.case_dir, {'commands': command_manifest})

            changes_total += status.metrics['n_changes']
            residual_points_total += len(residual_points_case)
            stages_total += len(case.stages)

            if residual_points_case:
                pd.DataFrame(residual_points_case).to_csv(built.case_dir / 'residuals.csv', index=False)

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
    ) -> RunStatus | None:
        if not case.stages:
            return None

        status: RunStatus | None = None
        last_target = None
        for idx, stage in enumerate(sorted(case.stages, key=lambda s: s.target_time), start=1):
            current_parameters['end_time'] = stage.target_time
            for change in stage.changes:
                current_parameters[change.parameter] = change.value
                changes_log.append(f'[{stage.stage_label}] {change.parameter} -> {change.value} @ {stage.target_time}')
            summary = self.template_engine.apply_parameters(case_dir, current_parameters)
            changes_log.extend(f'[{stage.stage_label}] arquivo alterado: {path}' for path in summary.files_touched)
            if summary.remaining_markers:
                raise ValueError(f'Marcadores remanescentes após {stage.stage_label} em {case.case_name}: {summary.remaining_markers}')

            command_sequence = self._build_stage_command_sequence(case, config, stage_label=stage.stage_label)
            result = self.runner.run_command_sequence(
                case_dir=case_dir,
                command_sequence=command_sequence,
                config=config,
                case_name=case.case_name,
                stdout_callback=stdout_callback,
                residual_callback=residual_callback,
                status_callback=status_callback,
                time_callback=time_callback,
                command_started_callback=command_started_callback,
            )
            command_manifest.extend([self.metadata_writer.to_serializable(record) for record in result.command_records])
            status = result.status
            last_target = stage.target_time
            if status.status == 'error':
                break
        if status is not None and last_target is not None:
            status.metrics['last_target_time'] = last_target
        return status

    def _build_command_sequence(self, case, config: ProjectConfig) -> list[dict[str, str]]:
        sequence: list[dict[str, str]] = []
        for command in self._parse_commands(config.internal_setup_commands):
            sequence.append({'phase': 'setup', 'label': command.split()[0], 'command': command})
        if not case.stages:
            for command in self._stage_commands(case, config):
                sequence.append({'phase': 'run', 'label': command.split()[0], 'command': command, 'stage_label': 'main'})
        return sequence

    def _build_post_sequence(self, case, config: ProjectConfig) -> list[dict[str, str]]:
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
        return commands if commands else ['foamRun']

    def _parse_commands(self, commands: list[str] | str) -> list[str]:
        if isinstance(commands, str):
            lines = commands.splitlines()
        else:
            lines = commands
        parsed = [str(line).strip() for line in lines if str(line).strip()]
        return parsed

    def _compute_campaign_metrics(self, changes_total: int, residual_points_total: int, stages_total: int) -> dict[str, Any]:
        total_cases = len(self.statuses)
        completed = sum(1 for s in self.statuses if s.status == 'completed')
        errors = sum(1 for s in self.statuses if s.status == 'error')
        interrupted = sum(1 for s in self.statuses if s.status == 'interrupted')
        wall_times = [float(s.metrics.get('wall_clock_seconds', 0.0)) for s in self.statuses]
        return {
            'total_cases': total_cases,
            'completed_cases': completed,
            'error_cases': errors,
            'interrupted_cases': interrupted,
            'campaign_wall_clock_seconds_total': sum(wall_times),
            'campaign_wall_clock_seconds_mean': (sum(wall_times) / total_cases) if total_cases else 0.0,
            'total_stages': stages_total,
            'total_changes': changes_total,
            'total_markers_found': len(self.preflight_report.markers) if self.preflight_report else 0,
            'total_markers_substituted': changes_total,
            'total_residual_points': residual_points_total,
        }
