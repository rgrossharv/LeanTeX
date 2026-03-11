from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from leantex.extractor import write_extracted_lean
from leantex.models import Snippet


class ExtractorTests(unittest.TestCase):
    def test_hoists_imports_and_preserves_line_count(self) -> None:
        snippets = [
            Snippet(index=1, code="example : True := by\n  trivial", start_line=1, end_line=2),
            Snippet(index=2, code="import Mathlib\n#check Nat", start_line=3, end_line=4),
        ]
        with TemporaryDirectory() as td:
            out = Path(td) / "Extracted.lean"
            extracted = write_extracted_lean(out, snippets)
            ranges = extracted.ranges
            text = out.read_text(encoding="utf-8")

        self.assertIn("import Mathlib", text)
        self.assertIn("-- LeanTeX hoisted import: import Mathlib", text)
        self.assertTrue(extracted.hoisted_import_line_to_stmt)
        # snippet 2 still has two lines in range after replacement
        self.assertEqual(ranges[1].end_line - ranges[1].start_line + 1, 2)

    def test_default_mode_wraps_snippet_in_namespace(self) -> None:
        snippets = [
            Snippet(index=1, code="theorem t1 : True := by trivial", start_line=1, end_line=1),
            Snippet(index=2, code="#check t1", start_line=2, end_line=2),
        ]
        with TemporaryDirectory() as td:
            out = Path(td) / "Extracted.lean"
            write_extracted_lean(out, snippets, shared_context=False)
            text = out.read_text(encoding="utf-8")

        self.assertIn("namespace LeanTeX_Snippet_1", text)
        self.assertIn("end LeanTeX_Snippet_1", text)
        self.assertIn("namespace LeanTeX_Snippet_2", text)

    def test_shared_context_mode_does_not_wrap_namespaces(self) -> None:
        snippets = [
            Snippet(index=1, code="theorem t1 : True := by trivial", start_line=1, end_line=1),
            Snippet(index=2, code="#check t1", start_line=2, end_line=2),
        ]
        with TemporaryDirectory() as td:
            out = Path(td) / "Extracted.lean"
            write_extracted_lean(out, snippets, shared_context=True)
            text = out.read_text(encoding="utf-8")

        self.assertNotIn("namespace LeanTeX_Snippet_", text)


if __name__ == "__main__":
    unittest.main()
