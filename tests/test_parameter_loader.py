from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.core.parameter_loader import ParameterLoader


def test_parameter_loader_primary_and_secondary():
    loader = ParameterLoader()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        primary_csv = tmp_path / "primary.csv"
        secondary_csv = tmp_path / "secondary.csv"

        primary_csv.write_text(
            "nome_do_caso,cfg__solver,viscosidade,nx\n"
            "case_001,interFoam,1e-6,50\n"
            "case_002,interFoam,2e-6,100\n",
            encoding="utf-8"
        )

        secondary_csv.write_text(
            "nome_do_caso,tempo,variavel,valor,stage\n"
            "case_001,0.5,viscosidade,1.5e-6,stage_1\n"
            "case_001,1.0,viscosidade,2.0e-6,stage_2\n",
            encoding="utf-8"
        )

        loaded = loader.load(primary_csv, secondary_csv)
        assert len(loaded.cases) == 2

        c1 = loaded.cases[0]
        assert c1.case_name == "case_001"
        assert c1.config_parameters.get("cfg__solver") == "interFoam"
        assert float(c1.template_parameters["viscosidade"]) == 1e-6
        assert c1.template_parameters["nx"] == "50"
        assert len(c1.stages) == 2
        assert c1.stages[0].target_time == 0.5
        assert c1.stages[0].changes[0].parameter == "viscosidade"
        assert float(c1.stages[0].changes[0].value) == 1.5e-6


def test_parameter_loader_missing_required_column():
    loader = ParameterLoader()
    with tempfile.TemporaryDirectory() as tmpdir:
        primary_csv = Path(tmpdir) / "invalid.csv"
        primary_csv.write_text("caso,viscosidade\ncase_01,1e-6\n", encoding="utf-8")

        with pytest.raises(ValueError, match="sem colunas obrigatórias"):
            loader.load(primary_csv)


def test_parameter_loader_descending_time():
    loader = ParameterLoader()
    with tempfile.TemporaryDirectory() as tmpdir:
        primary_csv = Path(tmpdir) / "primary.csv"
        primary_csv.write_text("nome_do_caso,visc\ncase_01,1e-6\n", encoding="utf-8")

        secondary_csv = Path(tmpdir) / "secondary.csv"
        secondary_csv.write_text(
            "nome_do_caso,tempo,variavel,valor\n"
            "case_01,2.0,visc,1e-5\n"
            "case_01,1.0,visc,2e-5\n",
            encoding="utf-8"
        )

        with pytest.raises(ValueError, match="Tempo decrescente detectado"):
            loader.load(primary_csv, secondary_csv)
