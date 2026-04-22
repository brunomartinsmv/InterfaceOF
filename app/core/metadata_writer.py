from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.run_status import RunStatus
from app.utils.file_ops import write_json, write_text


class MetadataWriter:
    def to_serializable(self, value: Any) -> Any:
        if is_dataclass(value):
            return self.to_serializable(asdict(value))
        if isinstance(value, dict):
            return {str(k): self.to_serializable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self.to_serializable(v) for v in value]
        if isinstance(value, Path):
            return str(value)
        return value

    def write_case_metadata(self, case_dir: Path, payload: dict[str, Any]) -> None:
        payload = self.to_serializable(payload)
        write_json(case_dir / 'case_info.json', payload)
        write_text(case_dir / 'case_info.txt', self._dict_to_text(payload))

    def write_case_log(self, case_dir: Path, payload: dict[str, Any]) -> None:
        payload = self.to_serializable(payload)
        write_json(case_dir / f'log_{case_dir.name}.json', payload)
        write_text(case_dir / f'log_{case_dir.name}.txt', self._dict_to_text(payload))

    def write_changes_log(self, case_dir: Path, lines: list[str]) -> None:
        write_text(case_dir / 'changes_log.txt', '\n'.join(lines) + ('\n' if lines else ''))

    def write_command_manifest(self, case_dir: Path, payload: dict[str, Any]) -> None:
        write_json(case_dir / 'logs' / 'command_manifest.json', self.to_serializable(payload))

    def write_campaign_metadata(self, campaign_dir: Path, payload: dict[str, Any], campaign_name: str) -> None:
        logs_dir = campaign_dir / 'logs'
        payload = self.to_serializable(payload)
        write_json(logs_dir / f'{campaign_name}.json', payload)
        write_text(logs_dir / f'{campaign_name}.txt', self._dict_to_text(payload))

    def _dict_to_text(self, payload: dict[str, Any]) -> str:
        lines: list[str] = []
        for key, value in payload.items():
            if is_dataclass(value):
                value = asdict(value)
            lines.append(f'{key}: {value}')
        lines.append(f'generated_at: {datetime.now().isoformat()}')
        return '\n'.join(lines)

    def serialize_status(self, status: RunStatus) -> dict[str, Any]:
        return {
            'case_name': status.case_name,
            'status': status.status,
            'start_time': status.start_time.isoformat() if status.start_time else None,
            'end_time': status.end_time.isoformat() if status.end_time else None,
            'last_simulated_time': status.last_simulated_time,
            'error_type': status.error_type,
            'error_message': status.error_message,
            'metrics': status.metrics,
        }
