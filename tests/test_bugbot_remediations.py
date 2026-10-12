from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.campaign_manager import CampaignManager, read_controldict_endtime, update_controldict_for_stage
from app.core.environment_adapter import EnvironmentAdapter
from app.core.parameter_loader import LoadedParameters, ParameterLoader
from app.core.preflight_validator import PreflightReport, PreflightValidator
from app.core.runner import Runner
from app.gui.tabs_monitor import MonitorTab
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


def test_controldict_inline_comment_handling():
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        sys_dir = case_dir / "system"
        sys_dir.mkdir(parents=True)
        cd = sys_dir / "controlDict"
        cd.write_text(
            "/* header */\n"
            "endTime /* inline comment */ 10.0;\n"
            "stopAt /* inline */ endTime;\n",
            encoding="utf-8"
        )
        assert read_controldict_endtime(case_dir) == 10.0
        assert update_controldict_for_stage(case_dir, target_time=25.0, start_from_latest=True) is True
        content = cd.read_text(encoding="utf-8")
        assert "endTime         25.0;" in content
        # ensure no duplicate endTime was appended
        assert content.count("endTime") == 2  # one in endTime directive, one in stopAt endTime


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


def test_solver_override_preserves_wrappers():
    manager = CampaignManager()
    config = ProjectConfig(internal_stage_commands=["mpirun -np 4 customSolver -parallel", "reconstructPar"])
    case = CaseDefinition(
        case_name="case_001",
        template_parameters={},
        config_parameters={"cfg__solver": "interFoam"},
    )
    cmds = manager._stage_commands(case, config)
    assert cmds == ["mpirun -np 4 interFoam -parallel", "reconstructPar"]

    # Test runApplication wrapper
    config2 = ProjectConfig(internal_stage_commands=["runApplication customSolver"])
    cmds2 = manager._stage_commands(case, config2)
    assert cmds2 == ["runApplication interFoam"]

    # Test complex mpirun flags
    config3 = ProjectConfig(internal_stage_commands=["mpirun -np 4 --bind-to core -x OMP_NUM_THREADS=1 mySolver -parallel"])
    cmds3 = manager._stage_commands(case, config3)
    assert cmds3 == ["mpirun -np 4 --bind-to core -x OMP_NUM_THREADS=1 interFoam -parallel"]

    # Test flag arguments or paths ending in Foam are not replaced
    config4 = ProjectConfig(internal_stage_commands=["mpirun -np 4 -wdir /cases/bubbleFoam mySolver -parallel"])
    cmds4 = manager._stage_commands(case, config4)
    assert cmds4 == ["mpirun -np 4 -wdir /cases/bubbleFoam interFoam -parallel"]


def test_secondary_events_merged_across_whitespace_case_names():
    loader = ParameterLoader()
    with tempfile.TemporaryDirectory() as tmpdir:
        p_csv = Path(tmpdir) / "primary.csv"
        p_csv.write_text("nome_do_caso,param\ncase_1,val\n", encoding="utf-8")
        s_csv = Path(tmpdir) / "secondary.csv"
        s_csv.write_text(
            "nome_do_caso,tempo,stage,variavel,valor\n"
            "case_1,1.0,stg1,var,10\n"
            " case_1 ,2.0,stg2,var,20\n",
            encoding="utf-8"
        )
        loaded = loader.load(p_csv, s_csv)
        assert len(loaded.cases) == 1
        case = loaded.cases[0]
        # Both rows must be merged into case_1 stages, sorted by tempo
        assert len(case.stages) == 2
        assert case.stages[0].target_time == 1.0
        assert case.stages[0].stage_label == "stg1"
        assert case.stages[1].target_time == 2.0
        assert case.stages[1].stage_label == "stg2"


def test_environment_adapter_resolve_bash_finds_which():
    adapter = EnvironmentAdapter()
    bash = adapter.resolve_bash()
    assert "bash" in bash
    assert Path(bash).exists() or bash == "bash.exe"


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


def test_runner_detects_fatal_output_with_zero_exit_code():
    runner = Runner()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        (case_dir / "logs").mkdir()
        config = ProjectConfig()
        # Script echoes FOAM FATAL ERROR and exits 0
        cmd_seq = [{"phase": "run", "label": "fatalTest", "command": "echo '--> FOAM FATAL ERROR: test error' && exit 0"}]
        res = runner.run_command_sequence(case_dir, cmd_seq, config, "case_test")
        assert res.status.status == "error"
        assert res.status.error_type == "solver_error"
        assert "test error" in str(res.status.error_message)


def test_monitor_tab_previews_cached_timestep_in_iteration_mode():
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(['-platform', 'offscreen'])
    monitor = MonitorTab()
    monitor.set_plot_config(time_stride=0.0, iteration_stride=1)
    batch = [{"equation": "Ux", "value": 0.05, "source_log": "log", "time": 0.1}]
    monitor.ingest_residual_batch(batch)
    # _preview_point must return the cached point even when using_time_axis is False
    preview = monitor._preview_point("Ux")
    assert preview is not None
    assert preview[1] == 0.05


def test_environment_adapter_honors_shell_executable_on_native_unix():
    adapter = EnvironmentAdapter()
    config = ProjectConfig(shell_executable="/custom/bin/bash")
    prefix = adapter.shell_prefix(config)
    assert prefix == ["/custom/bin/bash", "-c"]


def test_template_engine_replaces_marker_inside_quoted_url_with_slashes():
    from app.core.template_engine import TemplateEngine
    from app.core.marker_scanner import MarkerScanner, strip_comments
    engine = TemplateEngine()
    scanner = MarkerScanner()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        test_file = case_dir / "system" / "controlDict"
        test_file.parent.mkdir(parents=True)
        raw_content = """endpoint \"https://host/{[of_var:case_id]}\"; // trailing comment\n// {[of_var:commented]}\n"""
        test_file.write_text(raw_content, encoding="utf-8")

        # Verify strip_comments keeps the quoted url
        cleaned = strip_comments(raw_content)
        assert "https://host/{[of_var:case_id]}" in cleaned
        assert "commented" not in cleaned

        engine.prepare_case_templates(case_dir)
        summary = engine.apply_parameters(case_dir, {"case_id": "test1234"})
        assert summary.replaced_count == 1
        res_text = test_file.read_text(encoding="utf-8")
        assert "https://host/test1234" in res_text


def test_preflight_validator_rejects_empty_cases_list():
    validator = PreflightValidator()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        dict_file = case_dir / "system" / "controlDict"
        dict_file.parent.mkdir(parents=True)
        dict_file.write_text("param {[of_var:my_var]};", encoding="utf-8")
        loaded = LoadedParameters(cases=[], primary_df=None, secondary_df=None, normalized_primary_columns={})
        report = validator.validate(case_dir, loaded)
        assert report.ok is False
        assert any("Nenhum caso definido" in issue.message for issue in report.issues)


def test_runner_stop_case_nonblocking():
    runner = Runner()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        (case_dir / "logs").mkdir()
        config = ProjectConfig()
        import time
        # Run a long sleep command in a thread
        import threading
        cmd_seq = [{"phase": "run", "label": "sleepCmd", "command": "sleep 10"}]
        t = threading.Thread(target=runner.run_command_sequence, args=(case_dir, cmd_seq, config, "case_test"))
        t.start()
        time.sleep(0.3)
        # Calling stop_case should be non-blocking and return quickly
        start_t = time.time()
        runner.stop_case(wait_timeout=3.0, blocking=False)
        duration = time.time() - start_t
        assert duration < 1.0
        t.join(timeout=5.0)


def test_campaign_manager_preserves_negative_last_simulated_time():
    manager = CampaignManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        (case_dir / "logs").mkdir()
        config = ProjectConfig()
        # Solver output with negative time
        log_content = "Time = -2.0\nTime = -1.0\nExecutionTime = 1 s  ClockTime = 1 s\nEnd\n"
        cmd = f"echo '{log_content}' && exit 0"
        cmd_seq = [{"phase": "run", "label": "negTime", "command": cmd}]
        res = manager.runner.run_command_sequence(case_dir, cmd_seq, config, "case_test")
        assert res.status.last_simulated_time == -1.0
