from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.marker_scanner import MarkerScanner, strip_comments


def test_strip_comments_preserves_newlines():
    text = (
        "line 1\n"
        "/* block comment\n"
        "   spanning multiple\n"
        "   lines */\n"
        "line 5\n"
        "// single line comment\n"
        "line 7\n"
    )
    cleaned = strip_comments(text)
    assert "block comment" not in cleaned
    assert "single line comment" not in cleaned
    assert "line 1" in cleaned
    assert "line 5" in cleaned
    assert "line 7" in cleaned

    # A contagem de linhas deve ser estritamente preservada
    original_lines = text.splitlines()
    cleaned_lines = cleaned.splitlines()
    assert len(cleaned_lines) == len(original_lines)
    assert cleaned_lines[0].strip() == "line 1"
    assert cleaned_lines[4].strip() == "line 5"
    assert cleaned_lines[6].strip() == "line 7"


def test_scan_case_directory_ignores_comments_and_tracks_line_numbers():
    scanner = MarkerScanner()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        dict_file = case_dir / "system" / "blockMeshDict"
        dict_file.parent.mkdir(parents=True)

        content = (
            "/*\n"
            " * OpenFOAM banner\n"
            " * 3 lines header\n"
            " */\n"
            "// {[of_var:ignored_commented_var]}\n"
            "nx {[of_var:nx_cells]};\n"
            "ny {[of_var:ny_cells]};\n"
        )
        dict_file.write_text(content, encoding="utf-8")

        occurrences = scanner.scan_case_directory(case_dir)
        variables = {occ.variable: occ.line_number for occ in occurrences}

        assert "ignored_commented_var" not in variables
        assert "nx_cells" in variables
        assert "ny_cells" in variables

        # nx_cells está exatamente na linha 6
        assert variables["nx_cells"] == 6
        assert variables["ny_cells"] == 7
