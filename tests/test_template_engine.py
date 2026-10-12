from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.template_engine import TemplateEngine


def test_template_engine_caching_and_replacement():
    engine = TemplateEngine()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        system_dir = case_dir / "system"
        system_dir.mkdir(parents=True)

        dict_file = system_dir / "controlDict"
        dict_file.write_text(
            "// {[of_var:commented_marker]}\n"
            "endTime {[of_var:end_time]};\n"
            "deltaT {[of_var:delta_t]};\n",
            encoding="utf-8"
        )

        other_file = case_dir / "constant" / "transportProperties"
        other_file.parent.mkdir(parents=True)
        other_file.write_text("nu [0 2 -1 0 0 0 0] 1e-06;\n", encoding="utf-8")

        # Preparação de cache
        engine.prepare_case_templates(case_dir)
        cache_dir = case_dir / ".of_campaign_templates"
        assert cache_dir.is_dir()
        assert (cache_dir / "system" / "controlDict").is_file()
        assert not (cache_dir / "constant" / "transportProperties").exists()

        # Aplicação de parâmetros
        summary = engine.apply_parameters(case_dir, {"end_time": "10.0", "delta_t": "0.001"})
        assert summary.replaced_count == 2
        assert len(summary.remaining_markers) == 0

        updated_text = dict_file.read_text(encoding="utf-8")
        assert "endTime 10.0;" in updated_text
        assert "deltaT 0.001;" in updated_text
        assert "// {[of_var:commented_marker]}" in updated_text


def test_find_remaining_markers_ignores_comments():
    engine = TemplateEngine()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        dict_file = case_dir / "system" / "fvSolution"
        dict_file.parent.mkdir(parents=True)
        dict_file.write_text(
            "// {[of_var:comentado]}\n"
            "/* {[of_var:em_bloco]} */\n"
            "residual {[of_var:tolerancia]};\n",
            encoding="utf-8"
        )

        remaining = engine.find_remaining_markers(case_dir)
        assert remaining == ["tolerancia"]
