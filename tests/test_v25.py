"""Tests for the LeanTeX v2.5 native-minted pipeline."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from leantex.models import LeanMessage, Snippet
from leantex.render_v2 import write_generated_assets_v2


class V25RenderTests(unittest.TestCase):
    def test_output_only_block_does_not_write_code_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            gen = root / "leantexv2.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="#check Nat",
                    start_line=1,
                    end_line=1,
                    show="output",
                    source="macro",
                )
            ]

            write_generated_assets_v2(
                gen,
                snippets_dir,
                snippets,
                {1: [LeanMessage(severity="info", text="Nat : Type")]},
            )

            self.assertTrue((snippets_dir / "snippet_001.out.raw.txt").exists())
            self.assertFalse((snippets_dir / "snippet_001.code.raw.lean").exists())
            text = gen.read_text(encoding="utf-8")
            self.assertIn("LeanTeX v2.5", text)
            self.assertIn("leantex@outrawpath@1", text)
            self.assertNotIn("leantex@coderawpath@1", text)

    def test_named_minted_block_gets_lookup_entry(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            gen = root / "leantexv2.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="#check Nat",
                    start_line=1,
                    end_line=1,
                    name="natcheck",
                    show="output",
                    source="minted",
                )
            ]

            write_generated_assets_v2(gen, snippets_dir, snippets, {1: []})

            text = gen.read_text(encoding="utf-8")
            self.assertIn(r"leantex@named@natcheck\endcsname{1}", text)

    def test_prunes_stale_generated_snippet_files(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            gen = root / "leantexv2.generated.tex"
            snippets_dir = root / "snippets"
            snippets_dir.mkdir()
            stale = snippets_dir / "snippet_009.code.raw.lean"
            stale.write_text("old", encoding="utf-8")

            snippets = [
                Snippet(index=1, code="#check Nat", start_line=1, end_line=1)
            ]
            write_generated_assets_v2(gen, snippets_dir, snippets, {1: []})

            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
