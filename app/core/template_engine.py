from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.utils.file_ops import ensure_dir, write_json
from app.utils.normalizer import ensure_valid_token

MARKER_TEMPLATE = r"\{\[of_var:%s\]\}"
ANY_MARKER_RE = re.compile(r"\{\[of_var:([a-z0-9_]+)\]\}")
CACHE_DIRNAME = '.of_campaign_templates'
MANIFEST_NAME = 'manifest.json'


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
            if not ANY_MARKER_RE.search(text):
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
            new_text = template_text
            local_changes = 0
            for key, value in normalized.items():
                pattern = re.compile(MARKER_TEMPLATE % re.escape(key))
                new_text, count = pattern.subn(value, new_text)
                local_changes += count
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
            remaining.update(match.group(1) for match in ANY_MARKER_RE.finditer(text))
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
            if ANY_MARKER_RE.search(text):
                targets.append((path, text))
        return targets

    def _is_inside_cache(self, path: Path) -> bool:
        return CACHE_DIRNAME in path.parts
