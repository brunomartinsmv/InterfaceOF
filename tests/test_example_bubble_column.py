from __future__ import annotations

from pathlib import Path

from app.core.parameter_loader import ParameterLoader
from app.core.preflight_validator import PreflightValidator


def test_example_bubble_column_preflight():
    base_dir = Path(__file__).parent.parent / "examples" / "bubbleColumn"
    primary_csv = base_dir / "primary_parameters.csv"

    assert base_dir.is_dir()
    assert primary_csv.is_file()

    loader = ParameterLoader()
    validator = PreflightValidator()

    loaded = loader.load(primary_csv)
    assert len(loaded.cases) == 4
    assert [c.case_name for c in loaded.cases] == ["case_001", "case_002", "case_003", "case_004"]

    report = validator.validate(base_dir, loaded)
    assert report.ok is True
    # As variáveis encontradas devem ser d0, nx, ny
    marker_vars = {m.variable for m in report.markers}
    assert marker_vars == {"d0", "nx", "ny"}
