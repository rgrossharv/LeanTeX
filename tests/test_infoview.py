import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import leantex.infoview as infoview_mod
from leantex.infoview import (
    GoalSnapshot,
    _dedupe_goal_snapshots,
    _strip_markdown_fence,
    collect_plain_goals_with_document,
)
from leantex.models import SnippetRange


class InfoViewTests(unittest.TestCase):
    def test_strip_markdown_fence(self) -> None:
        raw = "```lean\n⊢ True\n```"
        self.assertEqual(_strip_markdown_fence(raw), "⊢ True")

    def test_dedupe_prefers_nontrivial_goals(self) -> None:
        snaps = [
            GoalSnapshot(kind="goal", snippet_line=1, rendered="no goals"),
            GoalSnapshot(kind="goal", snippet_line=2, rendered="no goals"),
            GoalSnapshot(kind="goal", snippet_line=3, rendered="⊢ 1 = 1"),
            GoalSnapshot(kind="goal", snippet_line=4, rendered="⊢ 1 = 1"),
        ]
        out = _dedupe_goal_snapshots(snaps)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].rendered, "⊢ 1 = 1")

    def test_keeps_term_goal_even_if_no_goals(self) -> None:
        snaps = [
            GoalSnapshot(kind="goal", snippet_line=1, rendered="no goals"),
            GoalSnapshot(kind="term", snippet_line=1, rendered="⊢ 1 + 1 = 2"),
        ]
        out = _dedupe_goal_snapshots(snaps)
        self.assertEqual(len(out), 2)

    def test_shared_context_queries_boundary_line(self) -> None:
        class FakeLspClient:
            calls: list[tuple[str, dict]] = []

            def __init__(self, cmd: list[str], cwd: Path) -> None:
                _ = cmd
                _ = cwd
                type(self).calls = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                _ = exc_type
                _ = exc
                _ = tb

            def notify(self, method: str, params) -> None:
                _ = method
                _ = params

            def request(self, method: str, params, timeout_s: float = 30.0):
                _ = timeout_s
                type(self).calls.append((method, params))
                if method == "$/lean/rpc/connect":
                    return {"sessionId": "fake"}
                if method == "$/lean/plainGoal":
                    return {"rendered": "no goals"}
                if method == "$/lean/plainTermGoal":
                    return {"goal": ""}
                if method == "$/lean/rpc/call":
                    return []
                return {}

        orig_client = infoview_mod.LspClient
        orig_cmd = infoview_mod._lean_server_cmd
        infoview_mod.LspClient = FakeLspClient
        infoview_mod._lean_server_cmd = lambda project_root: ["lean", "--server"]
        try:
            with TemporaryDirectory() as td:
                extracted = Path(td) / "Extracted.lean"
                extracted.write_text("a\nb\nc\nd\ne\nf\n", encoding="utf-8")
                ranges = [SnippetRange(index=1, start_line=3, end_line=4)]
                infoview_mod.collect_plain_goals(
                    project_root=Path(td),
                    extracted_lean=extracted,
                    ranges=ranges,
                    shared_context=True,
                )

            plain_goal_calls = [
                params for method, params in FakeLspClient.calls
                if method == "$/lean/plainGoal"
            ]
            self.assertEqual(len(plain_goal_calls), 1)
            self.assertEqual(plain_goal_calls[0]["position"]["line"], 4)
            self.assertEqual(plain_goal_calls[0]["position"]["character"], 0)

            rpc_calls = [
                params for method, params in FakeLspClient.calls
                if method == "$/lean/rpc/call"
            ]
            self.assertEqual(len(rpc_calls), 1)
            self.assertEqual(rpc_calls[0]["position"]["line"], 4)
            self.assertEqual(rpc_calls[0]["position"]["character"], 0)
        finally:
            infoview_mod.LspClient = orig_client
            infoview_mod._lean_server_cmd = orig_cmd

    def test_document_infoview_scans_full_extracted_file(self) -> None:
        class FakeLspClient:
            calls: list[tuple[str, dict]] = []

            def __init__(self, cmd: list[str], cwd: Path) -> None:
                _ = cmd
                _ = cwd
                type(self).calls = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                _ = exc_type
                _ = exc
                _ = tb

            def notify(self, method: str, params) -> None:
                _ = method
                _ = params

            def request(self, method: str, params, timeout_s: float = 30.0):
                _ = timeout_s
                type(self).calls.append((method, params))
                if method == "$/lean/rpc/connect":
                    return {"sessionId": "fake"}
                if method == "$/lean/plainGoal":
                    return {"rendered": "no goals"}
                if method == "$/lean/plainTermGoal":
                    return {"goal": ""}
                if method == "$/lean/rpc/call":
                    return []
                return {}

        orig_client = infoview_mod.LspClient
        orig_cmd = infoview_mod._lean_server_cmd
        infoview_mod.LspClient = FakeLspClient
        infoview_mod._lean_server_cmd = lambda project_root: ["lean", "--server"]
        try:
            with TemporaryDirectory() as td:
                extracted = Path(td) / "Extracted.lean"
                extracted.write_text("a\nb\nc\n", encoding="utf-8")
                ranges = [SnippetRange(index=1, start_line=2, end_line=2)]
                _, document_messages = collect_plain_goals_with_document(
                    project_root=Path(td),
                    extracted_lean=extracted,
                    ranges=ranges,
                    shared_context=True,
                )

            plain_goal_calls = [
                params for method, params in FakeLspClient.calls
                if method == "$/lean/plainGoal"
            ]
            queried_lines = [params["position"]["line"] for params in plain_goal_calls]
            self.assertIn(2, queried_lines)
            self.assertIn(0, queried_lines)
            self.assertIn(1, queried_lines)
            self.assertTrue(document_messages)
            self.assertIn("[infoview] tactic state:", document_messages[0].text)
        finally:
            infoview_mod.LspClient = orig_client
            infoview_mod._lean_server_cmd = orig_cmd


if __name__ == "__main__":
    unittest.main()
