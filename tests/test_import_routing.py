import unittest

from leantex.build import _route_global_import_messages
from leantex.models import LeanMessage, Snippet


class ImportRoutingTests(unittest.TestCase):
    def test_routes_hoisted_import_error_to_snippet(self) -> None:
        snippets = [
            Snippet(index=1, code="example : True := by trivial", start_line=1, end_line=1),
            Snippet(index=2, code="import Mathlib.Tactic\n#check Nat", start_line=2, end_line=3),
        ]
        by_snippet = {1: [], 2: []}
        global_messages = [
            LeanMessage(
                severity="error",
                text="unknown module prefix 'Mathlib'",
                line=3,
                col=0,
                source="json",
            )
        ]
        hoisted = {3: "import Mathlib.Tactic"}

        remaining = _route_global_import_messages(
            snippets=snippets,
            hoisted_import_line_to_stmt=hoisted,
            by_snippet=by_snippet,
            global_messages=global_messages,
        )

        self.assertEqual(len(remaining), 0)
        self.assertEqual(len(by_snippet[2]), 1)
        self.assertEqual(by_snippet[2][0].line, 1)
        self.assertEqual(by_snippet[2][0].col, 1)

    def test_routes_prefix_error_without_line(self) -> None:
        snippets = [
            Snippet(index=1, code="import Mathlib.Data.Real.Basic", start_line=1, end_line=1),
        ]
        by_snippet = {1: []}
        global_messages = [
            LeanMessage(
                severity="error",
                text="No directory 'Mathlib' or file 'Mathlib.olean' in the search path",
                source="json",
            )
        ]

        remaining = _route_global_import_messages(
            snippets=snippets,
            hoisted_import_line_to_stmt={},
            by_snippet=by_snippet,
            global_messages=global_messages,
        )

        self.assertEqual(len(remaining), 0)
        self.assertEqual(len(by_snippet[1]), 1)
        self.assertEqual(by_snippet[1][0].line, 1)


if __name__ == "__main__":
    unittest.main()
