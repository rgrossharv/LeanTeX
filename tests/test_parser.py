from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from leantex.parser import detect_shared_context_mode, detect_v2_mode, parse_tex_for_lean


class ParserTests(unittest.TestCase):
    def test_parses_blocks_and_ignores_commented_begin(self) -> None:
        text = r"""
% \begin{lean}
\begin{lean}[name=a,show=output]
#check Nat
\end{lean}

\begin{lean}
example : True := by trivial
\end{lean}
""".strip()
        with TemporaryDirectory() as td:
            p = Path(td) / "x.tex"
            p.write_text(text, encoding="utf-8")
            snippets = parse_tex_for_lean(p)

        self.assertEqual(len(snippets), 2)
        self.assertEqual(snippets[0].name, "a")
        self.assertEqual(snippets[0].show, "output")
        self.assertIn("#check Nat", snippets[0].code)
        self.assertIn("example : True", snippets[1].code)

    def test_parses_infoview_and_size_options(self) -> None:
        text = r"""
\begin{lean}[infoview=lines:3,codesize=footnotesize]
example : True := by trivial
\end{lean}
\begin{lean}[infoview=goals,codesize={\Large},outsize=tiny]
example : True := by trivial
\end{lean}
\begin{lean}[infoview=auto,size=scriptsize]
example : True := by trivial
\end{lean}
""".strip()
        with TemporaryDirectory() as td:
            p = Path(td) / "x.tex"
            p.write_text(text, encoding="utf-8")
            snippets = parse_tex_for_lean(p)

        self.assertEqual(snippets[0].infoview, "lines")
        self.assertEqual(snippets[0].infoview_lines, 3)
        self.assertEqual(snippets[0].code_size, r"\footnotesize")
        self.assertEqual(snippets[1].infoview, "goals")
        self.assertEqual(snippets[1].code_size, r"\Large")
        self.assertEqual(snippets[1].output_size, r"\tiny")
        self.assertEqual(snippets[2].code_size, r"\scriptsize")
        self.assertEqual(snippets[2].output_size, r"\scriptsize")

    def test_detects_shared_context_toggle_commands(self) -> None:
        text = r"""
\documentclass{article}
\usepackage{leantex}
\leantexenableonefile
\begin{document}
\begin{lean}
#check Nat
\end{lean}
\end{document}
""".strip()
        with TemporaryDirectory() as td:
            p = Path(td) / "x.tex"
            p.write_text(text, encoding="utf-8")
            shared = detect_shared_context_mode(p)
        self.assertTrue(shared)

    def test_detects_onefile_package_variants(self) -> None:
        text = r"""
\documentclass{article}
\usepackage[onefile]{leantex}
\usepackage{leantexonefile}
\begin{document}
\end{document}
""".strip()
        with TemporaryDirectory() as td:
            p = Path(td) / "x.tex"
            p.write_text(text, encoding="utf-8")
            shared = detect_shared_context_mode(p)
        self.assertTrue(shared)

    def test_toggle_defaults_off_and_disable_wins(self) -> None:
        text = r"""
\documentclass{article}
\usepackage[onefile]{leantex}
\leantexdisableonefile
\begin{document}
\end{document}
""".strip()
        with TemporaryDirectory() as td:
            p = Path(td) / "x.tex"
            p.write_text(text, encoding="utf-8")
            shared = detect_shared_context_mode(p)
        self.assertFalse(shared)

    def test_parses_leantex_macro_as_output_only_snippet(self) -> None:
        text = r"""
\documentclass{article}
\usepackage{leantexv2}
\begin{document}
\leantex[infoview=lines:2,outsize=tiny]{
#check Nat
example : { n : Nat // n = n } := by
  exact ⟨0, rfl⟩
}
\end{document}
""".strip()
        with TemporaryDirectory() as td:
            p = Path(td) / "x.tex"
            p.write_text(text, encoding="utf-8")
            snippets = parse_tex_for_lean(p)

        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0].show, "output")
        self.assertEqual(snippets[0].source, "macro")
        self.assertEqual(snippets[0].infoview, "lines")
        self.assertEqual(snippets[0].infoview_lines, 2)
        self.assertEqual(snippets[0].output_size, r"\tiny")
        self.assertIn("#check Nat", snippets[0].code)
        self.assertIn("{ n : Nat // n = n }", snippets[0].code)

    def test_parses_named_minted_lean_block_when_requested(self) -> None:
        text = r"""
\documentclass{article}
\usepackage{leantexv2}
\begin{document}
\leantexconfig{natcheck}{infoview=goals,outsize=scriptsize}
\begin{minted}[label=natcheck]{lean}
#check Nat
\end{minted}
\leantexoutput{natcheck}
\end{document}
""".strip()
        with TemporaryDirectory() as td:
            p = Path(td) / "x.tex"
            p.write_text(text, encoding="utf-8")
            snippets = parse_tex_for_lean(p, include_minted=True)

        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0].name, "natcheck")
        self.assertEqual(snippets[0].source, "minted")
        self.assertEqual(snippets[0].show, "output")
        self.assertEqual(snippets[0].infoview, "goals")
        self.assertEqual(snippets[0].output_size, r"\scriptsize")

    def test_v25_onefile_is_detected(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "x.tex"
            p.write_text(r"\usepackage[onefile]{leantexv2}", encoding="utf-8")

            self.assertTrue(detect_v2_mode(p))
            self.assertTrue(detect_shared_context_mode(p))


if __name__ == "__main__":
    unittest.main()
