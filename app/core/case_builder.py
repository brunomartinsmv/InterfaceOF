from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.template_engine import ReplacementSummary, TemplateEngine
from app.models.case_definition import CaseDefinition
from app.utils.file_ops import copy_case_directory, ensure_dir


@dataclass(slots=True)
class BuiltCase:
    case_dir: Path
    replacement_summary: ReplacementSummary


class CaseBuilder:
    def __init__(self, template_engine: TemplateEngine | None = None) -> None:
        self.template_engine = template_engine or TemplateEngine()

    def build(self, base_case_dir: Path, output_campaign_dir: Path, case: CaseDefinition) -> BuiltCase:
        case_dir = output_campaign_dir / case.case_name
        ensure_dir(output_campaign_dir)
        copy_case_directory(base_case_dir, case_dir)
        self.template_engine.prepare_case_templates(case_dir)
        replacement_summary = self.template_engine.apply_parameters(case_dir, case.template_parameters)
        return BuiltCase(case_dir=case_dir, replacement_summary=replacement_summary)
