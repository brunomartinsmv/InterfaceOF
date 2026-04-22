from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from app.models.run_status import RunStatus
from app.utils.file_ops import write_json


class SummaryWriter:
    def write_campaign_summary(self, summary_csv: Path, statuses: Iterable[RunStatus]) -> None:
        rows = []
        for status in statuses:
            row = {
                'case_name': status.case_name,
                'status': status.status,
                'start_time': status.start_time.isoformat() if status.start_time else None,
                'end_time': status.end_time.isoformat() if status.end_time else None,
                'last_simulated_time': status.last_simulated_time,
                'error_type': status.error_type,
                'error_message': status.error_message,
                **status.metrics,
            }
            if 'command_logs' in row and isinstance(row['command_logs'], list):
                row['command_logs'] = ' | '.join(str(v) for v in row['command_logs'])
            if 'log_error_messages' in row and isinstance(row['log_error_messages'], list):
                row['log_error_messages'] = ' | '.join(str(v) for v in row['log_error_messages'])
            rows.append(row)
        df = pd.DataFrame(rows)
        summary_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(summary_csv, index=False)

    def write_campaign_metrics(self, metrics_json: Path, payload: dict) -> None:
        write_json(metrics_json, payload)
