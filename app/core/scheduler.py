from __future__ import annotations

from dataclasses import dataclass

from app.models.case_definition import CaseDefinition
from app.models.stage_event import StageEvent


@dataclass(slots=True)
class ScheduledRun:
    case_name: str
    setup_parameters: dict[str, str]
    stages: list[StageEvent]


class Scheduler:
    def build_schedule(self, case: CaseDefinition) -> ScheduledRun:
        ordered_stages = sorted(case.stages, key=lambda evt: evt.target_time)
        return ScheduledRun(case_name=case.case_name, setup_parameters=case.template_parameters, stages=ordered_stages)
