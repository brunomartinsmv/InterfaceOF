from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.core.case_builder import CaseBuilder
from app.core.parameter_loader import ParameterLoader
from app.models.case_definition import CaseDefinition


def test_sanitize_case_name_rejects_traversal_and_invalid():
    loader = ParameterLoader()

    invalid_names = [
        "../escaped",
        "..\\escaped",
        "/absolute/path",
        "case/sub",
        "case\\sub",
        "",
        "   ",
        "nan",
        "NaN",
        ".",
        "..",
        "case<bad>",
        "case*star",
    ]

    for name in invalid_names:
        with pytest.raises(ValueError):
            loader.sanitize_case_name(name)


def test_case_builder_rejects_path_outside_campaign():
    builder = CaseBuilder()
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "base"
        campaign_dir = Path(tmpdir) / "campaign"
        base_dir.mkdir()
        (base_dir / "system").mkdir()
        (base_dir / "system" / "controlDict").write_text("FoamFile {};\n", encoding="utf-8")

        # Escaped case definition
        escaped_case = CaseDefinition(
            case_name="../escaped",
            template_parameters={},
            config_parameters={},
        )

        with pytest.raises(ValueError, match="inseguro ou fora da campanha"):
            builder.build(base_dir, campaign_dir, escaped_case)


def test_loader_rejects_duplicate_case_names():
    loader = ParameterLoader()
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "primary.csv"
        csv_path.write_text(
            "nome_do_caso,viscosidade\n"
            "case_001,1e-6\n"
            "case_001,2e-6\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Caso duplicado"):
            loader.load(csv_path)


def test_loader_rejects_duplicate_raw_headers():
    loader = ParameterLoader()
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "primary.csv"
        csv_path.write_text(
            "nome_do_caso,viscosidade,viscosidade\n"
            "case_001,1e-6,2e-6\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Cabeçalho duplicado"):
            loader.load(csv_path)


def test_loader_rejects_secondary_case_not_in_primary():
    loader = ParameterLoader()
    with tempfile.TemporaryDirectory() as tmpdir:
        p_csv = Path(tmpdir) / "primary.csv"
        p_csv.write_text(
            "nome_do_caso,viscosidade\n"
            "case_001,1e-6\n",
            encoding="utf-8",
        )
        s_csv = Path(tmpdir) / "secondary.csv"
        s_csv.write_text(
            "nome_do_caso,tempo,variavel,valor\n"
            "case_unknown,0.5,viscosidade,2e-6\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="não existe no CSV primário"):
            loader.load(p_csv, s_csv)
