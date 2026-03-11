from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


class TeXInstallError(RuntimeError):
    pass


LATEXMK_BLOCK_START = "# >>> LeanTeX auto-hook >>>"
LATEXMK_BLOCK_END = "# <<< LeanTeX auto-hook <<<"


def detect_texmfhome() -> Path:
    kpsewhich = shutil.which("kpsewhich")
    if kpsewhich:
        proc = subprocess.run(
            [kpsewhich, "-var-value=TEXMFHOME"],
            text=True,
            capture_output=True,
            check=False,
        )
        value = proc.stdout.strip()
        if proc.returncode == 0 and value:
            return Path(os.path.expanduser(value))
    return Path.home() / "texmf"


def _latexmk_hook_block(python_executable: str) -> str:
    py = python_executable.replace("\\", "\\\\").replace("'", "\\'")
    project_root = str(Path(__file__).resolve().parent.parent)
    project_root = project_root.replace("\\", "\\\\").replace("'", "\\'")
    return (
        f"{LATEXMK_BLOCK_START}\n"
        "my $leantex_python = '" + py + "';\n"
        "my $leantex_root = '" + project_root + "';\n"
        "my $leantex_wrapper = \"env PYTHONPATH='$leantex_root' $leantex_python -m leantex latexmk-run\";\n"
        "$pdflatex = \"$leantex_wrapper pdflatex %O %S\";\n"
        "$xelatex = \"$leantex_wrapper xelatex %O %S\";\n"
        "$lualatex = \"$leantex_wrapper lualatex %O %S\";\n"
        f"{LATEXMK_BLOCK_END}\n"
    )


def install_latexmkrc(
    python_executable: str | None = None,
    home: Path | None = None,
) -> Path:
    target_home = home.expanduser().resolve() if home is not None else Path.home()
    rc_path = target_home / ".latexmkrc"

    existing = ""
    if rc_path.exists():
        try:
            existing = rc_path.read_text(encoding="utf-8")
        except OSError:
            existing = ""

    block_re = re.compile(
        re.escape(LATEXMK_BLOCK_START)
        + r"[\s\S]*?"
        + re.escape(LATEXMK_BLOCK_END)
        + r"\n?",
        flags=re.MULTILINE,
    )
    cleaned = block_re.sub("", existing).rstrip()
    block = _latexmk_hook_block(python_executable or sys.executable)

    out = block if not cleaned else (cleaned + "\n\n" + block)
    rc_path.write_text(out, encoding="utf-8")
    return rc_path


def install_sty(dest_root: Path | None = None) -> Path:
    tex_dir = Path(__file__).resolve().parent.parent / "tex"
    src_main = tex_dir / "leantex.sty"
    src_onefile = tex_dir / "leantexonefile.sty"
    if not src_main.exists():
        raise TeXInstallError(f"missing style file: {src_main}")
    if not src_onefile.exists():
        raise TeXInstallError(f"missing style file: {src_onefile}")

    root = dest_root.resolve() if dest_root else detect_texmfhome().resolve()
    dest_dir = root / "tex" / "latex" / "leantex"
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / "leantex.sty"
    dest_onefile = dest_dir / "leantexonefile.sty"
    shutil.copy2(src_main, dest)
    shutil.copy2(src_onefile, dest_onefile)

    mktexlsr = shutil.which("mktexlsr")
    if mktexlsr:
        subprocess.run([mktexlsr, str(root)], check=False)

    install_latexmkrc()

    return dest
