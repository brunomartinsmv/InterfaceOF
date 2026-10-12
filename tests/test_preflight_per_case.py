from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.parameter_loader import LoadedParameters
from app.core.preflight_validator import PreflightValidator
from app.models.case_definition import CaseDefinition


def test_preflight_validator_detects_variable_missing_in_specific_case():
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        dict_file = case_dir / "dict"
        dict_file.write_text("x {[of_var:x]};\ny {[of_var:y]};\n", encoding="utf-8")

        # Case A has both x and y. Case B has only x.
        case_a = CaseDefinition(case_name="case_a", template_parameters={"x": "1", "y": "2"}, config_parameters={})
        case_b = CaseDefinition(case_name="case_b", template_parameters={"x": "1"}, config_parameters={})

        loaded = LoadedParameters(
            primary_df=None,
            secondary_df=None,
            cases=[case_a, case_b],
            normalized_primary_columns={},
        )

        validator = PreflightValidator()
        report = validator.validate(case_dir, loaded)

        assert report.ok is False
        error_msgs = [i.message for i in report.issues if i.severity == "error"]
        assert any("Marcador sem valor inicial no caso 'case_b': y" in msg for msg in error_msgs)
