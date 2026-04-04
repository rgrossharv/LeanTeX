from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from leantex.models import Snippet
from leantex.render import write_generated_assets
from leantex.models import LeanMessage


class GeneratedAssetsTests(unittest.TestCase):
    def test_emits_code_and_output_size_macros(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            generated = root / "leantex.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="example : True := by trivial",
                    start_line=1,
                    end_line=3,
                    code_size=r"\footnotesize",
                    output_size=r"\tiny",
                )
            ]

            write_generated_assets(generated, snippets_dir, snippets, {1: []})

            text = generated.read_text(encoding="utf-8")
            self.assertIn(r"\csname leantex@codesize@1\endcsname{\footnotesize}", text)
            self.assertIn(r"\csname leantex@outsize@1\endcsname{\tiny}", text)
            self.assertIn(r"\csname leantex@coderawpath@1\endcsname{", text)
            self.assertIn(r"\csname leantex@outrawpath@1\endcsname{", text)

    def test_emits_dynamic_unicode_mapping_for_unknown_symbols(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            generated = root / "leantex.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="example : 𝔸 := by sorry",
                    start_line=1,
                    end_line=3,
                )
            ]

            write_generated_assets(generated, snippets_dir, snippets, {1: []})

            text = generated.read_text(encoding="utf-8")
            self.assertIn(
                r"\csname leantex@unicode@1D538\endcsname{\ensuremath{\mathbb{A}}}",
                text,
            )
            self.assertIn(r"\leantexsetdynamicliterate{", text)
            self.assertIn(r"{U+1D538}{{\leantexunicodemapped{1D538}}}7", text)
            code = (snippets_dir / "snippet_001.code.lean").read_text(encoding="utf-8")
            self.assertIn("U+1D538", code)
            raw_code = (snippets_dir / "snippet_001.code.raw.lean").read_text(encoding="utf-8")
            self.assertIn("𝔸", raw_code)

    def test_emits_unicode_math_table_mapping_when_available(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            generated = root / "leantex.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="example : (fun x => x) = (fun x => x) := by\n  -- mapsto\n  #check (fun x ↦ x)",
                    start_line=1,
                    end_line=4,
                )
            ]

            write_generated_assets(generated, snippets_dir, snippets, {1: []})
            text = generated.read_text(encoding="utf-8")
            self.assertIn(r"\csname leantex@unicode@21A6\endcsname", text)
            self.assertIn(r"{U+21A6}{{\leantexunicodemapped{21A6}}}6", text)

    def test_prefers_direct_bullet_mapping_over_undefined_unicode_math_command(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            generated = root / "leantex.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="#check 3 • x",
                    start_line=1,
                    end_line=2,
                )
            ]

            write_generated_assets(generated, snippets_dir, snippets, {1: []})
            text = generated.read_text(encoding="utf-8")
            self.assertIn(
                r"\csname leantex@unicode@2022\endcsname{\ensuremath{\bullet}}",
                text,
            )

    def test_lowercase_double_struck_k_uses_bbbk(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            generated = root / "leantex.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="variable (𝕜 : Type)",
                    start_line=1,
                    end_line=2,
                )
            ]

            write_generated_assets(generated, snippets_dir, snippets, {1: []})
            text = generated.read_text(encoding="utf-8")
            self.assertIn(
                r"\csname leantex@unicode@1D55C\endcsname{\ensuremath{\Bbbk}}",
                text,
            )

    def test_lowercase_double_struck_letter_falls_back_to_roman(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            generated = root / "leantex.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="#check 𝕒",
                    start_line=1,
                    end_line=2,
                )
            ]

            write_generated_assets(generated, snippets_dir, snippets, {1: []})
            text = generated.read_text(encoding="utf-8")
            self.assertIn(
                r"\csname leantex@unicode@1D552\endcsname{\ensuremath{\mathrm{a}}}",
                text,
            )

    def test_emits_document_level_extracted_infoview_assets(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            generated = root / "leantex.generated.tex"
            snippets_dir = root / "snippets"
            snippets = [
                Snippet(
                    index=1,
                    code="#check Nat.succ",
                    start_line=1,
                    end_line=2,
                )
            ]
            document_messages = [
                LeanMessage(
                    severity="error",
                    line=5,
                    col=1,
                    text="unknown identifier 'x'",
                    source="lean",
                ),
                LeanMessage(
                    severity="info",
                    line=6,
                    col=1,
                    text="[infoview] tactic state:\nno goals",
                    source="infoview",
                ),
            ]

            write_generated_assets(
                generated,
                snippets_dir,
                snippets,
                {1: []},
                document_messages=document_messages,
            )

            text = generated.read_text(encoding="utf-8")
            self.assertIn(r"\csname leantex@extractedoutpath\endcsname{", text)
            self.assertIn(r"\csname leantex@extractedoutrawpath\endcsname{", text)
            self.assertIn(r"\csname leantex@extractedhaserror\endcsname{1}", text)
            output = (root / "extracted.infoview.txt").read_text(encoding="utf-8")
            self.assertIn("=== Messages ===", output)
            self.assertIn("=== Infoview State ===", output)


if __name__ == "__main__":
    unittest.main()
