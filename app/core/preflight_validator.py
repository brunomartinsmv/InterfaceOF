from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.marker_scanner import MarkerOccurrence, MarkerScanner
from app.core.parameter_loader import LoadedParameters
from app.models.case_definition import CaseDefinition


@dataclass(slots=True)
class ValidationIssue:
    severity: str
    message: str


@dataclass(slots=True)
class VariableAuditRow:
    variable: str
    file_path: str
    line_number: int
    status: str
    origin: str


@dataclass(slots=True)
class PreflightReport:
    markers: list[MarkerOccurrence]
    issues: list[ValidationIssue] = field(default_factory=list)
    audit_rows: list[VariableAuditRow] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.severity == 'error' for issue in self.issues)


class PreflightValidator:
    def __init__(self, scanner: MarkerScanner | None = None) -> None:
        self.scanner = scanner or MarkerScanner()

    def validate(self, case_dir: Path, loaded: LoadedParameters) -> PreflightReport:
        markers = self.scanner.scan_case_directory(case_dir)
        report = PreflightReport(markers=markers)

        marker_names = {m.variable for m in markers}
        all_primary = set().union(*(case.template_parameters.keys() for case in loaded.cases)) if loaded.cases else set()
        all_secondary = set()
        for case in loaded.cases:
            for stage in case.stages:
                for change in stage.changes:
                    all_secondary.add(change.parameter)

        all_supplied = all_primary | all_secondary

        for marker in markers:
            status = 'ok' if marker.variable in all_supplied else 'faltando_no_csv'
            report.audit_rows.append(VariableAuditRow(marker.variable, str(marker.file_path), marker.line_number,
                                                      status, 'marcador_no_caso'))

        missing = sorted(marker_names - all_supplied)
        extras = sorted(all_supplied - marker_names)

        for name in missing:
            report.issues.append(ValidationIssue('error', f'Marcador sem valor correspondente nos CSVs: {name}'))

        for name in extras:
            report.issues.append(ValidationIssue('warning', f'Variável presente nos CSVs sem marcador correspondente: {name}'))
            report.audit_rows.append(VariableAuditRow(name, '', 0, 'sobrando_no_csv', 'csv'))

        self._validate_cases(loaded.cases, report)
        return report

    def _validate_cases(self, cases: list[CaseDefinition], report: PreflightReport) -> None:
        for case in cases:
            seen_times: list[float] = []
            for stage in case.stages:
                if stage.target_time < 0:
                    report.issues.append(ValidationIssue('error', f'Tempo negativo no caso {case.case_name}: {stage.target_time}'))
                if seen_times and stage.target_time < seen_times[-1]:
                    report.issues.append(ValidationIssue('error', f'Tempo decrescente no caso {case.case_name}.'))
                seen_times.append(stage.target_time)
                for change in stage.changes:
                    if not str(change.value).strip():
                        report.issues.append(ValidationIssue('error', f'Valor vazio em evento secundário: {case.case_name}/{change.parameter}'))
