from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from leantex.build import _load_cache, _save_cache
from leantex.models import BuildContext, LeanMessage


class CacheTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            ctx = BuildContext(
                tex_path=root / "x.tex",
                tex_dir=root,
                project_root=root,
                generated_dir=root / "LeanTeX",
                extracted_lean_path=root / "LeanTeX" / "Extracted.lean",
                generated_tex_path=root / "leantex.generated.tex",
                snippets_dir=root / "LeanTeX" / "snippets",
                output_dir=root / "LeanTeX",
            )

            signature = {"schema": 1, "project_root": str(root), "extracted_sha256": "abc"}
            by_snippet = {
                1: [LeanMessage(severity="info", text="ok", line=1, col=1, source="plain")],
            }
            globals_ = [LeanMessage(severity="warning", text="note", source="build")]
            document = [LeanMessage(severity="info", text="doc", line=3, col=1, source="infoview")]

            _save_cache(
                context=ctx,
                signature=signature,
                by_snippet=by_snippet,
                document_messages=document,
                global_messages=globals_,
                raw_output="stdout text",
            )

            loaded = _load_cache(ctx, signature)
            self.assertIsNotNone(loaded)
            if loaded is None:
                return
            loaded_by, loaded_document, loaded_globals, loaded_raw = loaded
            self.assertEqual(loaded_raw, "stdout text")
            self.assertEqual(len(loaded_by[1]), 1)
            self.assertEqual(loaded_by[1][0].text, "ok")
            self.assertEqual(len(loaded_document), 1)
            self.assertEqual(loaded_document[0].text, "doc")
            self.assertEqual(len(loaded_globals), 1)
            self.assertEqual(loaded_globals[0].severity, "warning")

    def test_load_miss_on_signature_change(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            ctx = BuildContext(
                tex_path=root / "x.tex",
                tex_dir=root,
                project_root=root,
                generated_dir=root / "LeanTeX",
                extracted_lean_path=root / "LeanTeX" / "Extracted.lean",
                generated_tex_path=root / "leantex.generated.tex",
                snippets_dir=root / "LeanTeX" / "snippets",
                output_dir=root / "LeanTeX",
            )

            _save_cache(
                context=ctx,
                signature={"schema": 1, "project_root": str(root), "extracted_sha256": "abc"},
                by_snippet={},
                document_messages=[],
                global_messages=[],
                raw_output="",
            )
            miss = _load_cache(
                ctx,
                {"schema": 1, "project_root": str(root), "extracted_sha256": "different"},
            )
            self.assertIsNone(miss)


if __name__ == "__main__":
    unittest.main()
