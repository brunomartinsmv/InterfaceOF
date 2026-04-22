from __future__ import annotations

from dataclasses import dataclass
import re

TIME_RE = re.compile(r'^Time\s*=\s*([0-9eE+\-.]+)')
ERROR_PATTERNS = [
    re.compile(r'Floating point exception', re.IGNORECASE),
    re.compile(r'Segmentation fault', re.IGNORECASE),
    re.compile(r'FOAM FATAL ERROR', re.IGNORECASE),
    re.compile(r'FOAM FATAL IO ERROR', re.IGNORECASE),
    re.compile(r'command not found', re.IGNORECASE),
]


@dataclass(slots=True)
class LogEvent:
    current_time: float | None = None
    error_detected: bool = False
    error_message: str | None = None


class LogParser:
    def parse_line(self, line: str) -> LogEvent:
        event = LogEvent()
        if match := TIME_RE.search(line.strip()):
            try:
                event.current_time = float(match.group(1))
            except ValueError:
                event.current_time = None
        for pattern in ERROR_PATTERNS:
            if pattern.search(line):
                event.error_detected = True
                event.error_message = line.strip()
                break
        return event
