from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.core.campaign_manager import CampaignManager
from app.models.case_definition import CaseDefinition
from app.models.project_config import ProjectConfig
from app.models.stage_event import StageChange, StageEvent


def test_campaign_manager_rejects_allrun_with_stages():
    manager = CampaignManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "base"
        out_dir = Path(tmpdir) / "out"
        base_dir.mkdir()
        (base_dir / "system").mkdir()
        (base_dir / "system" / "controlDict").write_text("FoamFile {};\n", encoding="utf-8")
        (base_dir / "0").mkdir()

        p_csv = base_dir / "p.csv"
        p_csv.write_text("nome_do_caso,cfg__runner_mode\ncase_001,allrun\n", encoding="utf-8")
        s_csv = base_dir / "s.csv"
        s_csv.write_text("nome_do_caso,tempo,variavel,valor\ncase_001,0.5,var,1\n", encoding="utf-8")

        config = ProjectConfig(
            base_case_dir=base_dir,
            primary_csv=p_csv,
            secondary_csv=s_csv,
            output_dir=out_dir,
            runner_mode="allrun",
        )

        with pytest.raises(ValueError, match="não é compatível com simulação multiestágio"):
            manager.run_campaign(config)


def test_campaign_manager_multistage_log_numbering_and_isolation():
    manager = CampaignManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "base"
        out_dir = Path(tmpdir) / "out"
        base_dir.mkdir()
        (base_dir / "system").mkdir()
        (base_dir / "system" / "controlDict").write_text(
            "application test;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\nendTime 1.0;\n",
            encoding="utf-8",
        )
        dict_file = base_dir / "constant" / "params"
        dict_file.parent.mkdir()
        dict_file.write_text("val {[of_var:val]};\n", encoding="utf-8")

        p_csv = base_dir / "primary.csv"
        p_csv.write_text("nome_do_caso,val\ncase_001,10\n", encoding="utf-8")
        s_csv = base_dir / "secondary.csv"
        s_csv.write_text(
            "nome_do_caso,tempo,variavel,valor,stage\n"
            "case_001,0.5,val,20,stg1\n"
            "case_001,1.0,val,30,stg2\n",
            encoding="utf-8",
        )

        config = ProjectConfig(
            base_case_dir=base_dir,
            primary_csv=p_csv,
            secondary_csv=s_csv,
            output_dir=out_dir,
            runner_mode="internal",
            activation_enabled=False,
            internal_setup_commands=["echo setup_mesh"],
            internal_stage_commands=["echo run_solver"],
            internal_post_commands=["echo post_process"],
        )

        campaign_dir = manager.run_campaign(config)
        case_dir = campaign_dir / "case_001"
        logs_dir = case_dir / "logs"

        assert logs_dir.is_dir()
        log_files = sorted(f.name for f in logs_dir.glob("*.log"))

        # Verify logs are uniquely indexed and not overwritten
        # 001_setup, 002_stage_initial, 003_stage_stg1, 004_post
        assert len(log_files) >= 3
        assert any("001_setup" in name for name in log_files)
        assert any("002_stage" in name for name in log_files)
        assert any("003_stage" in name for name in log_files)

        # Verify statuses
        assert len(manager.statuses) == 1
        status = manager.statuses[0]
        assert status.status == "completed"
        assert status.metrics["executed_stages"] >= 1
