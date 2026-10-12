from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.template_engine import TemplateEngine


def test_template_engine_literal_backslash_and_comment_protection():
    engine = TemplateEngine()
    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir)
        dict_file = case_dir / "someDict"
        dict_file.write_text(
            "/*\n"
            "   commented: {[of_var:path]}\n"
            "*/\n"
            "// line commented: {[of_var:path]}\n"
            "activePath \"{[of_var:path]}\";\n"
            "regexPattern \"{[of_var:bad_pattern]}\";\n",
            encoding="utf-8"
        )

        engine.prepare_case_templates(case_dir)

        # Values containing backslashes and regex escape sequences
        params = {
            "path": r"C:\tmp\openfoam\test\1",
            "bad_pattern": r"\g<missing_group>\t\n",
        }

        summary = engine.apply_parameters(case_dir, params)
        assert summary.replaced_count == 2
        assert not summary.remaining_markers

        content = dict_file.read_text(encoding="utf-8")
        # Markers inside comments must be preserved exactly
        assert "commented: {[of_var:path]}" in content
        assert "line commented: {[of_var:path]}" in content

        # Active markers must be replaced literally
        assert r'activePath "C:\tmp\openfoam\test\1";' in content
        assert r'regexPattern "\g<missing_group>\t\n";' in content
