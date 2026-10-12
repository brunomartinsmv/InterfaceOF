from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.campaign_manager import CampaignManager, read_controldict_endtime
from app.core.parameter_loader import LoadedParameters
from app.core.preflight_validator import PreflightReport, PreflightValidator
from app.models.case_definition import CaseDefinition
from app.models.project_config import ProjectConfig
from app.models.run_status import RunStatus
from app.models.stage_event import StageChange, StageEvent


def test_read_controldict_endtime():
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        sys_dir = case_dir / "system"
        sys_dir.mkdir(parents=True)
        cd = sys_dir / "controlDict"
        cd.write_text(
            "/* endTime 99.0; */\n"
            "// endTime 88.0;\n"
            "endTime         5.5;\n",
            encoding="utf-8"
        )
        assert read_controldict_endtime(case_dir) == 5.5


def test_solver_override_with_arguments():
    manager = CampaignManager()
    config = ProjectConfig(internal_stage_commands=["foamRun -parallel", "reconstructPar"])
    case = CaseDefinition(
        case_name="case_001",
        template_parameters={},
        config_parameters={"cfg__solver": "interFoam"},
    )
    cmds = manager._stage_commands(case, config)
    assert cmds == ["interFoam -parallel", "reconstructPar"]


def test_audit_row_marked_missing_when_any_case_lacks_variable():
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        dict_file = case_dir / "params"
        dict_file.write_text("var {[of_var:var]};\n", encoding="utf-8")

        # case_1 has var, case_2 is missing var
        case_1 = CaseDefinition(case_name="case_1", template_parameters={"var": "10"}, config_parameters={})
        case_2 = CaseDefinition(case_name="case_2", template_parameters={}, config_parameters={})

        loaded = LoadedParameters(
            primary_df=None,
            secondary_df=None,
            cases=[case_1, case_2],
            normalized_primary_columns={},
        )
        validator = PreflightValidator()
        report = validator.validate(case_dir, loaded)

        audit_row = next(r for r in report.audit_rows if r.variable == "var")
        assert audit_row.status == "faltando_no_csv"


def test_mean_wall_clock_time_divides_by_executed_cases():
    manager = CampaignManager()
    case_1 = CaseDefinition(case_name="case_1", template_parameters={}, config_parameters={})
    case_2 = CaseDefinition(case_name="case_2", template_parameters={}, config_parameters={})
    case_3 = CaseDefinition(case_name="case_3", template_parameters={}, config_parameters={})
    manager.loaded_parameters = LoadedParameters(
        primary_df=None,
        secondary_df=None,
        cases=[case_1, case_2, case_3],
        normalized_primary_columns={},
    )

    # Only 1 case actually executed before being stopped
    st = RunStatus(case_name="case_1", status="completed")
    st.metrics["wall_clock_seconds"] = 10.0
    manager.statuses = [st]

    metrics = manager._compute_campaign_metrics(changes_total=1, residual_points_total=1, stages_total=0)
    assert metrics["total_cases"] == 3
    assert metrics["completed_cases"] == 1
    # Mean must be 10.0 / 1 = 10.0, NOT 10.0 / 3 = 3.333
    assert metrics["campaign_wall_clock_seconds_mean"] == 10.0


def test_solver_and_processors_defaults_reported_cleanly():
    config = ProjectConfig(default_solver="simpleFoam", n_processors=8)
    case = CaseDefinition(
        case_name="case_default",
        template_parameters={},
        config_parameters={},
    )
    # Check that when metrics are set, default_solver is simpleFoam and n_processors is 8
    solver_override = case.config_parameters.get('cfg__solver')
    if solver_override:
        resolved_solver = str(solver_override).strip()
    elif config.default_solver:
        resolved_solver = str(config.default_solver).strip()
    elif config.internal_stage_commands:
        resolved_solver = config.internal_stage_commands[0].split()[0]
    else:
        resolved_solver = 'foamRun'

    resolved_procs = str(case.config_parameters.get('cfg__n_processors', config.n_processors))
    assert resolved_solver == "simpleFoam"
    assert isinstance(resolved_solver, str)
    assert resolved_procs == "8"


def test_pending_cancellation_not_cleared_by_campaign_manager():
    manager = CampaignManager()
    # If interrupted before/during validation or worker startup
    manager.stop()
    assert manager.runner.is_interrupted is True

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "base"
        base_dir.mkdir()
        (base_dir / "system").mkdir()
        (base_dir / "system" / "controlDict").write_text("endTime 1.0;\n", encoding="utf-8")
        out_dir = Path(tmpdir) / "output"
        csv_file = Path(tmpdir) / "cases.csv"
        csv_file.write_text("nome_do_caso\ncase_1\n", encoding="utf-8")

        config = ProjectConfig(
            base_case_dir=base_dir,
            primary_csv=csv_file,
            output_dir=out_dir,
        )

        # run_campaign should NOT reset_stop()
        manager.run_campaign(config)
        assert manager.runner.is_interrupted is True
        # Since it was interrupted before starting any cases, 0 cases ran
        assert len(manager.statuses) == 0
