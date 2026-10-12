from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.utils.normalizer import ensure_valid_token

MARKER_RE = re.compile(r"\{\[of_var:([a-z0-9_]+)\]\}")
C_TOKEN_RE = re.compile(r"(\"(?:\\.|[^\"\\\\])*\")|(/\*.*?\*/)|(//[^\n]*)", flags=re.DOTALL)


def strip_comments(text: str) -> str:
    """Remove comentarios C/C++ (// e /* */) preservando quebras de linha e strings entre aspas."""
    def _rep(match: re.Match[str]) -> str:
        string_literal = match.group(1)
        if string_literal is not None:
            return string_literal
        block_comment = match.group(2)
        if block_comment is not None:
            return re.sub(r"[^\n]", " ", block_comment)
        line_comment = match.group(3)
        return " " * len(line_comment)

    return C_TOKEN_RE.sub(_rep, text)

@dataclass(slots=True)
class MarkerOccurrence:
    variable: str
    file_path: Path
    line_number: int
    raw_match: str


class MarkerScanner:
    def scan_case_directory(self, case_dir: Path) -> list[MarkerOccurrence]:
        occurrences: list[MarkerOccurrence] = []
        for path in sorted(case_dir.rglob('*')):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            stripped = self._remove_comments(text)
            for line_number, line in enumerate(stripped.splitlines(), start=1):
                for match in MARKER_RE.finditer(line):
                    variable = ensure_valid_token(match.group(1))
                    occurrences.append(MarkerOccurrence(variable, path, line_number, match.group(0)))
        return occurrences

    def _remove_comments(self, text: str) -> str:
        return strip_comments(text)
