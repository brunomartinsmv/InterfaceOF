from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class CampaignPaths:
    campaign_dir: Path
    logs_dir: Path
    summary_csv: Path
    metrics_json: Path
    config_json: Path


def timestamp_label() -> str:
    return datetime.now().strftime('%Y-%m-%d_%H%M%S')


def build_campaign_paths(output_dir: Path) -> CampaignPaths:
    tag = f'campaign_{timestamp_label()}'
    campaign_dir = output_dir / tag
    logs_dir = campaign_dir / 'logs'
    return CampaignPaths(
        campaign_dir=campaign_dir,
        logs_dir=logs_dir,
        summary_csv=campaign_dir / 'campaign_summary.csv',
        metrics_json=campaign_dir / 'campaign_metrics.json',
        config_json=campaign_dir / 'campaign_config.json',
    )
