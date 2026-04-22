from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class StageChange:
    parameter: str
    value: str


@dataclass(slots=True)
class StageEvent:
    case_name: str
    target_time: float
    stage_label: str
    changes: list[StageChange]
