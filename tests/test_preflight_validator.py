from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.parameter_loader import ParameterLoader
from app.core.preflight_validator import PreflightValidator


def test_preflight_validator_ok():
    validator = PreflightValidator()
    loader = ParameterLoader()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        case_dir = tmp_path / "case_template"
        case_dir.mkdir()
        dict_file = case_dir / "system_param"
        dict_file.write_text("visc {[of_var:viscosidade]}; nx {[of_var:nx]};\n", encoding="utf-8")

        primary_csv = tmp_path / "primary.csv"
        primary_csv.write_text("nome_do_caso,viscosidade,nx\ncase_01,1e-6,100\n", encoding="utf-8")

        loaded = loader.load(primary_csv)
        report = validator.validate(case_dir, loaded)

        assert report.ok is True
        assert len(report.issues) == 0


def test_preflight_validator_missing_variable():
    validator = PreflightValidator()
    loader = ParameterLoader()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        case_dir = tmp_path / "case_template"
        case_dir.mkdir()
        dict_file = case_dir / "system_param"
        dict_file.write_text("visc {[of_var:viscosidade]}; ny {[of_var:ny]};\n", encoding="utf-8")

        primary_csv = tmp_path / "primary.csv"
        primary_csv.write_text("nome_do_caso,viscosidade\ncase_01,1e-6\n", encoding="utf-8")

        loaded = loader.load(primary_csv)
        report = validator.validate(case_dir, loaded)

        assert report.ok is False
        error_msgs = [i.message for i in report.issues if i.severity == "error"]
        assert any("ny" in msg for msg in error_msgs)
