from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from leantex.build import _sync_generated_workspace
from leantex.models import Snippet


class WorkspaceTests(unittest.TestCase):
    def test_sync_generated_workspace_links_only_needed_sources(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            project_root = root / "proj"
            generated_dir = root / "texdoc" / "LeanTeX"
            project_root.mkdir(parents=True)
            (project_root / "lakefile.toml").write_text('name = "Proj"\n', encoding="utf-8")
            (project_root / "lean-toolchain").write_text("leanprover/lean4:v4.27.0\n", encoding="utf-8")
            (project_root / "lake-manifest.json").write_text("{}", encoding="utf-8")
            (project_root / ".lake").mkdir()
            (project_root / "Proj.lean").write_text("def x := 1\n", encoding="utf-8")
            (project_root / "Proj").mkdir()
            (project_root / "Proj" / "Basic.lean").write_text("#check Nat\n", encoding="utf-8")
            (project_root / "MIL").mkdir()
            (project_root / "MIL" / "Demo.lean").write_text("#check Nat\n", encoding="utf-8")
            (project_root / "MIL.lean").write_text("import MIL.Demo\n", encoding="utf-8")
            (project_root / "mathematics_in_lean").mkdir()
            (project_root / "mathematics_in_lean" / "Unused.lean").write_text("#check Nat\n", encoding="utf-8")

            snippets = [
                Snippet(
                    index=1,
                    code="import Mathlib.Data.Real.Basic\nimport Proj.Basic",
                    start_line=1,
                    end_line=2,
                )
            ]

            _sync_generated_workspace(generated_dir, project_root, snippets)

            self.assertTrue((generated_dir / "lakefile.toml").exists())
            self.assertTrue((generated_dir / "lean-toolchain").exists())
            self.assertTrue((generated_dir / ".lake").exists())
            self.assertTrue((generated_dir / "Proj.lean").exists())
            self.assertTrue((generated_dir / "Proj").exists())
            self.assertFalse((generated_dir / "MIL").exists())
            self.assertFalse((generated_dir / "MIL.lean").exists())
            self.assertFalse((generated_dir / "mathematics_in_lean").exists())


if __name__ == "__main__":
    unittest.main()
