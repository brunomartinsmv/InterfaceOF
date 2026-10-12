from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.marker_scanner import strip_comments
from app.utils.file_ops import ensure_dir, write_json
from app.utils.normalizer import ensure_valid_token

ANY_MARKER_RE = re.compile(r"\{\[of_var:([a-z0-9_]+)\]\}")
CACHE_DIRNAME = '.of_campaign_templates'
MANIFEST_NAME = 'manifest.json'

COMMENT_OR_MARKER_RE = re.compile(
    r'(/\*.*?\*/)|(//[^\n]*)|(\{\[of_var:([a-z0-9_]+)\]\})',
    flags=re.DOTALL
)


@dataclass(slots=True)
class ReplacementSummary:
    replaced_count: int
    files_touched: list[str]
    remaining_markers: list[str]


class TemplateEngine:
    def prepare_case_templates(self, case_dir: Path) -> None:
        cache_dir = case_dir / CACHE_DIRNAME
        manifest_path = cache_dir / MANIFEST_NAME
        if manifest_path.exists():
            return

        entries: list[str] = []
        for path in sorted(case_dir.rglob('*')):
            if not path.is_file() or self._is_inside_cache(path):
                continue
            try:
                text = path.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            clean = strip_comments(text)
            if not ANY_MARKER_RE.search(clean):
                continue
            rel = path.relative_to(case_dir)
            cached = cache_dir / rel
            ensure_dir(cached.parent)
            cached.write_text(text, encoding='utf-8')
            entries.append(str(rel).replace('\\', '/'))
        write_json(manifest_path, {'files': entries})

    def apply_parameters(self, case_dir: Path, parameters: dict[str, object]) -> ReplacementSummary:
        normalized = {ensure_valid_token(k): str(v) for k, v in parameters.items()}
        replaced_count = 0
        files_touched: list[str] = []

        targets = self._target_files(case_dir)
        for path, template_text in targets:
            local_changes = 0

            def _replace_match(match: re.Match[str]) -> str:
                nonlocal local_changes
                block_comment = match.group(1)
                line_comment = match.group(2)
                if block_comment is not None:
                    return block_comment
                if line_comment is not None:
                    return line_comment

                var_name = match.group(4)
                if var_name in normalized:
                    local_changes += 1
                    return normalized[var_name]
                return match.group(0)

            new_text = COMMENT_OR_MARKER_RE.sub(_replace_match, template_text)
            if local_changes:
                path.write_text(new_text, encoding='utf-8')
                replaced_count += local_changes
                files_touched.append(str(path))

        remaining = self.find_remaining_markers(case_dir)
        return ReplacementSummary(replaced_count, files_touched, remaining)

    def find_remaining_markers(self, case_dir: Path) -> list[str]:
        remaining: set[str] = set()
        for path in sorted(case_dir.rglob('*')):
            if not path.is_file() or self._is_inside_cache(path):
                continue
            try:
                text = path.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            clean = strip_comments(text)
            remaining.update(match.group(1) for match in ANY_MARKER_RE.finditer(clean))
        return sorted(remaining)

    def _target_files(self, case_dir: Path) -> list[tuple[Path, str]]:
        cache_dir = case_dir / CACHE_DIRNAME
        manifest_path = cache_dir / MANIFEST_NAME
        targets: list[tuple[Path, str]] = []
        if manifest_path.exists():
            try:
                payload = json.loads(manifest_path.read_text(encoding='utf-8'))
                files = payload.get('files', [])
            except Exception:
                files = []
            for rel in files:
                target = case_dir / rel
                cached = cache_dir / rel
                if not cached.is_file():
                    continue
                try:
                    template_text = cached.read_text(encoding='utf-8', errors='ignore')
                except OSError:
                    continue
                targets.append((target, template_text))
            if targets:
                return targets

        for path in sorted(case_dir.rglob('*')):
            if not path.is_file() or self._is_inside_cache(path):
                continue
            try:
                text = path.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            clean = strip_comments(text)
            if ANY_MARKER_RE.search(clean):
                targets.append((path, text))
        return targets

    def _is_inside_cache(self, path: Path) -> bool:
        return CACHE_DIRNAME in path.parts
