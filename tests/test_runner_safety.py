from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.core.runner import Runner
from app.models.project_config import ProjectConfig


def test_runner_cleans_up_process_on_callback_exception():
    runner = Runner()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        config = ProjectConfig(activation_enabled=False)

        def failing_callback(_line: str):
            raise RuntimeError("GUI callback crashed!")

        with pytest.raises(RuntimeError, match="GUI callback crashed!"):
            runner.run_command_sequence(
                case_dir=case_dir,
                command_sequence=[{"phase": "run", "label": "sleeper", "command": "sleep 10"}],
                config=config,
                case_name="case_crash",
                stdout_callback=failing_callback,
            )

        # Process must be cleaned up and set to None
        assert runner._process is None


def test_runner_unique_log_names_across_sequences():
    runner = Runner()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        config = ProjectConfig(activation_enabled=False)

        res1 = runner.run_command_sequence(
            case_dir=case_dir,
            command_sequence=[{"phase": "setup", "label": "mesh", "command": "echo meshing"}],
            config=config,
            case_name="case_001",
            start_index=1,
        )

        res2 = runner.run_command_sequence(
            case_dir=case_dir,
            command_sequence=[{"phase": "stage", "label": "solve", "stage_label": "stg1", "command": "echo solving"}],
            config=config,
            case_name="case_001",
            start_index=2,
        )

        log1 = Path(res1.command_records[0].log_path)
        log2 = Path(res2.command_records[0].log_path)

        assert log1.name == "001_setup_mesh.log"
        assert log2.name == "002_stage_stg1_solve.log"
        assert log1.exists()
        assert log2.exists()
        assert log1 != log2
