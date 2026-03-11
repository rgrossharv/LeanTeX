from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from leantex.texinstall import (
    LATEXMK_BLOCK_END,
    LATEXMK_BLOCK_START,
    install_latexmkrc,
)


class TeXInstallTests(unittest.TestCase):
    def test_install_latexmkrc_writes_hook_block(self) -> None:
        with TemporaryDirectory() as td:
            home = Path(td)
            rc = install_latexmkrc(
                python_executable="/usr/bin/python3",
                home=home,
            )
            text = rc.read_text(encoding="utf-8")

        self.assertIn(LATEXMK_BLOCK_START, text)
        self.assertIn(LATEXMK_BLOCK_END, text)
        self.assertIn("-m leantex latexmk-run", text)

    def test_install_latexmkrc_is_idempotent(self) -> None:
        with TemporaryDirectory() as td:
            home = Path(td)
            rc = home / ".latexmkrc"
            rc.write_text("my $pdf_mode = 1;\n", encoding="utf-8")

            install_latexmkrc(
                python_executable="/usr/bin/python3",
                home=home,
            )
            first = rc.read_text(encoding="utf-8")

            install_latexmkrc(
                python_executable="/usr/local/bin/python3",
                home=home,
            )
            second = rc.read_text(encoding="utf-8")

        self.assertIn("my $pdf_mode = 1;", second)
        self.assertEqual(second.count(LATEXMK_BLOCK_START), 1)
        self.assertIn("/usr/local/bin/python3", second)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
