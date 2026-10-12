from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.campaign_manager import detect_latest_time, update_controldict_for_stage


def test_update_controldict_does_not_modify_commented_directives():
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        sys_dir = case_dir / "system"
        sys_dir.mkdir(parents=True)
        control_dict = sys_dir / "controlDict"

        # controlDict containing endTime and startFrom inside comments
        control_dict.write_text(
            "/*\n"
            "   endTime 100.0;\n"
            "   startFrom latestTime;\n"
            "*/\n"
            "// endTime 200.0;\n"
            "application interFoam;\n"
            "startTime 0;\n",
            encoding="utf-8"
        )

        res = update_controldict_for_stage(case_dir, target_time=0.5, start_from_latest=True)
        assert res is True

        content = control_dict.read_text(encoding="utf-8")
        # Comments must remain intact
        assert "endTime 100.0;" in content
        assert "endTime 200.0;" in content

        # Active lines must be appended outside comments
        assert "endTime         0.5;" in content
        assert "stopAt          endTime;" in content
        assert "startFrom       latestTime;" in content


def test_detect_latest_time_handles_parallel_processor_directories():
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        (case_dir / "0").mkdir()
        (case_dir / "0.2").mkdir()

        # Parallel processor directories
        p0 = case_dir / "processor0"
        p1 = case_dir / "processor1"
        p0.mkdir()
        p1.mkdir()
        (p0 / "0.5").mkdir()
        (p0 / "1.8").mkdir()
        (p1 / "1.8").mkdir()

        latest = detect_latest_time(case_dir)
        assert latest == 1.8
