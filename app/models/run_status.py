from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class RunStatus:
    case_name: str
    status: str = 'queued'
    start_time: datetime | None = None
    end_time: datetime | None = None
    last_simulated_time: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
