from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.stage_event import StageEvent


@dataclass(slots=True)
class CaseDefinition:
    case_name: str
    template_parameters: dict[str, Any]
    config_parameters: dict[str, Any] = field(default_factory=dict)
    stages: list[StageEvent] = field(default_factory=list)
    output_dir: Path | None = None
