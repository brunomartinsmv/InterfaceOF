from __future__ import annotations

from dataclasses import dataclass
import re

RESIDUAL_RE = re.compile(
    r"Solving for\s+([^,]+),\s+Initial residual\s*=\s*([0-9eE+\-.]+)(?:,\s+Final residual\s*=\s*([0-9eE+\-.]+))?"
)


@dataclass(slots=True)
class ResidualPoint:
    equation: str
    initial_residual: float
    final_residual: float | None = None


class ResidualParser:
    def parse_line(self, line: str) -> ResidualPoint | None:
        match = RESIDUAL_RE.search(line)
        if not match:
            return None
        equation = match.group(1).strip()
        initial = float(match.group(2))
        final = float(match.group(3)) if match.group(3) else None
        return ResidualPoint(equation=equation, initial_residual=initial, final_residual=final)
