from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.campaign_manager import (
    CampaignManager,
    detect_latest_time,
    update_controldict_for_stage,
)
from app.models.run_status import RunStatus


def test_update_controldict_for_stage():
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        sys_dir = case_dir / "system"
        sys_dir.mkdir(parents=True)
        control_dict = sys_dir / "controlDict"
        control_dict.write_text(
            "startFrom startTime;\n"
            "startTime 0;\n"
            "stopAt endTime;\n"
            "endTime 1.0;\n",
            encoding="utf-8"
        )

        # Atualizar para estágio 1 (sem start_from_latest)
        res1 = update_controldict_for_stage(case_dir, target_time=0.5, start_from_latest=False)
        assert res1 is True
        c1 = control_dict.read_text(encoding="utf-8")
        assert "endTime         0.5;" in c1
        assert "startFrom startTime;" in c1

        # Atualizar para estágio 2 (com start_from_latest)
        res2 = update_controldict_for_stage(case_dir, target_time=2.0, start_from_latest=True)
        assert res2 is True
        c2 = control_dict.read_text(encoding="utf-8")
        assert "endTime         2.0;" in c2
        assert "startFrom       latestTime;" in c2


def test_detect_latest_time():
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        (case_dir / "0").mkdir()
        (case_dir / "0.5").mkdir()
        (case_dir / "1.25").mkdir()
        (case_dir / "constant").mkdir()
        (case_dir / "system").mkdir()

        latest = detect_latest_time(case_dir)
        assert latest == 1.25


def test_compute_campaign_metrics_and_stop():
    manager = CampaignManager()
    manager.statuses = [
        RunStatus(case_name="case_001", status="completed"),
        RunStatus(case_name="case_002", status="interrupted"),
        RunStatus(case_name="case_003", status="error"),
    ]
    metrics = manager._compute_campaign_metrics(changes_total=5, residual_points_total=20, stages_total=2)

    assert metrics["total_cases"] == 3
    assert metrics["completed_cases"] == 1
    assert metrics["interrupted_cases"] == 1
    assert metrics["error_cases"] == 1
    assert metrics["total_changes"] == 5

    manager.stop()
    assert manager.runner.is_interrupted is True
    manager.reset_stop()
    assert manager.runner.is_interrupted is False
