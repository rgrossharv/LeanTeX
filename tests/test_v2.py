"""Tests for LeanTeX v2 (minted-based) pipeline."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from leantex.models import LeanMessage, Snippet
from leantex.parser import detect_v2_mode, detect_shared_context_mode
from leantex.render_v2 import write_generated_assets_v2


class V2DetectionTests(unittest.TestCase):
    def _write_tex(self, td: str, content: str) -> Path:
        p = Path(td) / "test.tex"
        p.write_text(content, encoding="utf-8")
        return p

    def test_detects_leantexv2_package(self) -> None:
        with TemporaryDirectory() as td:
            p = self._write_tex(td, r"\usepackage{leantexv2}")
            self.assertTrue(detect_v2_mode(p))

    def test_detects_leantexv2_with_onefile_option(self) -> None:
        with TemporaryDirectory() as td:
            p = self._write_tex(td, r"\usepackage[onefile]{leantexv2}")
            self.assertTrue(detect_v2_mode(p))
            self.assertTrue(detect_shared_context_mode(p))

    def test_detects_leantexv2onefile_package(self) -> None:
        with TemporaryDirectory() as td:
            p = self._write_tex(td, r"\usepackage{leantexv2onefile}")
            self.assertTrue(detect_v2_mode(p))
            self.assertTrue(detect_shared_context_mode(p))

    def test_v1_not_detected_as_v2(self) -> None:
        with TemporaryDirectory() as td:
            p = self._write_tex(td, r"\usepackage{leantex}")
            self.assertFalse(detect_v2_mode(p))

    def test_v1_onefile_not_detected_as_v2(self) -> None:
        with TemporaryDirectory() as td:
            p = self._write_tex(td, r"\usepackage[onefile]{leantex}")
            self.assertFalse(detect_v2_mode(p))
            self.assertTrue(detect_shared_context_mode(p))


class V2RenderTests(unittest.TestCase):
    def test_generates_raw_utf8_files_only(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            gen = root / "leantexv2.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="example : \u2200 x, x = x := by rfl",
                    start_line=1,
                    end_line=1,
                )
            ]
            write_generated_assets_v2(gen, snippets_dir, snippets, {1: []})

            # Raw file should contain actual Unicode
            raw = (snippets_dir / "snippet_001.code.raw.lean").read_text(encoding="utf-8")
            self.assertIn("\u2200", raw)

            # No sanitized .code.lean file should exist (only .code.raw.lean)
            self.assertFalse((snippets_dir / "snippet_001.code.lean").exists())

    def test_generated_tex_has_no_literate_mappings(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            gen = root / "leantexv2.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="\u03b1 \u2192 \u03b2",
                    start_line=1,
                    end_line=1,
                )
            ]
            write_generated_assets_v2(gen, snippets_dir, snippets, {1: []})

            text = gen.read_text(encoding="utf-8")
            # No literate mapping machinery
            self.assertNotIn("leantexsetdynamicliterate", text)
            self.assertNotIn("leantexunicodemapped", text)
            # Should have v2 header
            self.assertIn("LeanTeX v2", text)

    def test_haserror_flag_set_correctly(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            gen = root / "leantexv2.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(index=1, code="x", start_line=1, end_line=1),
                Snippet(index=2, code="y", start_line=2, end_line=2),
            ]
            msgs = {
                1: [],
                2: [LeanMessage(severity="error", text="fail")],
            }
            write_generated_assets_v2(gen, snippets_dir, snippets, msgs)
            text = gen.read_text(encoding="utf-8")
            self.assertIn(r"leantex@haserror@1\endcsname{0}", text)
            self.assertIn(r"leantex@haserror@2\endcsname{1}", text)

    def test_code_and_output_sizes_emitted(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            gen = root / "leantexv2.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="x",
                    start_line=1,
                    end_line=1,
                    code_size=r"\footnotesize",
                    output_size=r"\tiny",
                )
            ]
            write_generated_assets_v2(gen, snippets_dir, snippets, {1: []})
            text = gen.read_text(encoding="utf-8")
            self.assertIn(r"\footnotesize", text)
            self.assertIn(r"\tiny", text)

    def test_extracted_infoview_written(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            gen = root / "leantexv2.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [Snippet(index=1, code="x", start_line=1, end_line=1)]
            doc_msgs = [LeanMessage(severity="info", text="all good")]
            write_generated_assets_v2(gen, snippets_dir, snippets, {1: []}, doc_msgs)

            text = gen.read_text(encoding="utf-8")
            self.assertIn("extractedoutrawpath", text)
            self.assertIn("extractedhaserror", text)

            extracted = (root / "extracted.infoview.raw.txt").read_text(encoding="utf-8")
            self.assertIn("all good", extracted)


if __name__ == "__main__":
    unittest.main()
