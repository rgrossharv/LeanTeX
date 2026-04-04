import unittest

from leantex.models import LeanMessage
from leantex.render import (
    _annotate_code_for_display,
    format_messages,
)


class RenderTests(unittest.TestCase):
    def test_collapses_long_infoview_state_to_messages(self) -> None:
        msgs = [
            LeanMessage(
                severity="info",
                line=1,
                col=1,
                source="infoview",
                text="[infoview] tactic state:\nline1\nline2\nline3\nline4\nline5",
            ),
            LeanMessage(
                severity="warning",
                line=2,
                col=1,
                source="infoview-message",
                text="[infoview message] end warning",
            ),
        ]

        out = format_messages(msgs)
        self.assertNotIn("=== Infoview State ===", out)
        self.assertIn("=== Infoview Messages ===", out)
        self.assertIn("end warning", out)

    def test_keeps_short_infoview_state(self) -> None:
        msgs = [
            LeanMessage(
                severity="info",
                line=1,
                col=1,
                source="infoview",
                text="[infoview] tactic state:\nno goals",
            )
        ]
        out = format_messages(msgs)
        self.assertIn("=== Infoview State ===", out)

    def test_preserves_code_without_checkmarks(self) -> None:
        code = "\n".join(
            [
                "example : 1 + 1 = 2 := by rfl",
                "theorem t : False := by",
                "  exact False.elim ?h",
                "lemma ok : True := by trivial",
            ]
        )
        msgs = [
            LeanMessage(
                severity="error",
                line=3,
                col=3,
                source="plain",
                text="unknown identifier '?h'",
            )
        ]
        annotated = _annotate_code_for_display(code, msgs)
        self.assertEqual(annotated, code)

    def test_infoview_goals_mode_only_shows_goals_accomplished(self) -> None:
        msgs = [
            LeanMessage(
                severity="info",
                line=1,
                col=1,
                source="infoview",
                text="[infoview] tactic state:\nline1\nline2",
            ),
            LeanMessage(
                severity="warning",
                line=2,
                col=1,
                source="infoview-message",
                text="[infoview message] style lint warning",
            ),
            LeanMessage(
                severity="info",
                line=3,
                col=1,
                source="infoview-message",
                text="[infoview message] Goals accomplished!",
            ),
        ]
        out = format_messages(msgs, infoview_mode="goals")
        self.assertIn("Goals accomplished!", out)
        self.assertNotIn("style lint warning", out)
        self.assertNotIn("=== Infoview State ===", out)

    def test_infoview_lines_mode_truncates_state(self) -> None:
        msgs = [
            LeanMessage(
                severity="info",
                line=1,
                col=1,
                source="infoview",
                text="[infoview] tactic state:\na\nb\nc\nd",
            ),
            LeanMessage(
                severity="info",
                line=2,
                col=1,
                source="infoview-message",
                text="[infoview message] Goals accomplished!",
            ),
        ]
        out = format_messages(msgs, infoview_mode="lines", infoview_lines=3)
        self.assertIn("=== Infoview State (first 3 line(s)) ===", out)
        self.assertIn("... (2 more line(s) hidden)", out)
        self.assertIn("Goals accomplished!", out)


if __name__ == "__main__":
    unittest.main()
