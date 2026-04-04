from __future__ import annotations

import argparse
import re
import sys
import time
import threading
from collections.abc import Callable
from pathlib import Path
import subprocess

from .build import process, run_latexmk
from .runner import LeanToolMissingError
from .texinstall import TeXInstallError, install_sty

USEPACKAGE_LINE_RE = re.compile(
    r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{(?P<pkgs>[^}]*)\}",
    flags=re.IGNORECASE,
)


def _print_summary(tex_path: Path, snippet_count: int) -> None:
    print(f"[leantex] processed {snippet_count} snippet(s) from {tex_path}")


def _run_with_progress(label: str, fn: Callable[[], object]) -> object:
    result: dict[str, object] = {}
    error: dict[str, BaseException] = {}
    done = threading.Event()
    is_tty = sys.stdout.isatty()

    def _target() -> None:
        try:
            result["value"] = fn()
        except BaseException as exc:  # pragma: no cover - passthrough from worker
            error["value"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    start = time.monotonic()
    width = 24
    pos = 0
    direction = 1

    if not is_tty:
        print(f"[leantex] {label}...")

    while not done.wait(0.12):
        if not is_tty:
            continue
        elapsed = time.monotonic() - start
        cells = [" "] * width
        cells[pos] = "="
        if pos + 1 < width:
            cells[pos + 1] = ">"
        bar = "".join(cells)
        print(
            f"\r[leantex] {label} [{bar}] {elapsed:5.1f}s",
            end="",
            flush=True,
        )
        pos += direction
        if pos <= 0 or pos >= width - 2:
            direction *= -1

    thread.join()
    elapsed = time.monotonic() - start
    if is_tty:
        print(
            f"\r[leantex] {label} [{'#' * width}] {elapsed:5.1f}s done"
        )
    else:
        print(f"[leantex] {label} complete ({elapsed:.1f}s)")

    if "value" in error:
        raise error["value"]
    return result.get("value")


def _strip_tex_comment(line: str) -> str:
    idx = line.find("%")
    if idx == -1:
        return line
    return line[:idx]


def _tex_uses_leantex(tex_path: Path) -> bool:
    try:
        lines = tex_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for raw in lines:
        line = _strip_tex_comment(raw)
        if not line.strip():
            continue
        for m in USEPACKAGE_LINE_RE.finditer(line):
            pkgs = [p.strip() for p in m.group("pkgs").split(",") if p.strip()]
            if any(p in pkgs for p in ("leantex", "leantexonefile", "leantexv2", "leantexv2onefile")):
                return True
    return False


def cmd_build(args: argparse.Namespace) -> int:
    tex_path = Path(args.tex_path)
    if not tex_path.exists():
        print(f"[leantex] error: file not found: {tex_path}", file=sys.stderr)
        return 2

    try:
        project_root = Path(args.project_root).expanduser() if args.project_root else None
        result = _run_with_progress(
            "running Lean pipeline",
            lambda: process(tex_path, project_root_override=project_root),
        )
        _print_summary(tex_path, len(result.snippets))
        if result.global_messages:
            print("[leantex] global messages:")
            for msg in result.global_messages:
                if msg.line is not None and msg.col is not None:
                    loc = f"{msg.line}:{msg.col}: "
                else:
                    loc = ""
                print(f"  - [{msg.severity}] {loc}{msg.text}")
    except LeanToolMissingError as exc:
        print(f"[leantex] error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - cli fallback
        print(f"[leantex] error: {exc}", file=sys.stderr)
        return 1

    if not args.no_latexmk:
        try:
            _run_with_progress(
                "building PDF with latexmk",
                lambda: run_latexmk(tex_path.resolve()),
            )
            print("[leantex] latexmk build complete")
        except Exception as exc:
            print(f"[leantex] error: {exc}", file=sys.stderr)
            return 1

    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    tex_path = Path(args.tex_path).resolve()
    if not tex_path.exists():
        print(f"[leantex] error: file not found: {tex_path}", file=sys.stderr)
        return 2

    interval = args.interval
    print(f"[leantex] watching {tex_path} every {interval:.1f}s")

    last_mtime = -1.0
    while True:
        try:
            mtime = tex_path.stat().st_mtime
            if mtime != last_mtime:
                last_mtime = mtime
                rc = cmd_build(
                    argparse.Namespace(
                        tex_path=str(tex_path),
                        no_latexmk=args.no_latexmk,
                        project_root=args.project_root,
                    )
                )
                if rc != 0:
                    print("[leantex] build failed; waiting for next change", file=sys.stderr)
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[leantex] watch stopped")
            return 0


def cmd_install_tex(args: argparse.Namespace) -> int:
    dest = Path(args.dest).expanduser() if args.dest else None
    try:
        installed = install_sty(dest)
    except TeXInstallError as exc:
        print(f"[leantex] error: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"[leantex] error: permission denied installing package: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - cli fallback
        print(f"[leantex] error: {exc}", file=sys.stderr)
        return 1

    print(f"[leantex] installed LaTeX package to {installed}")
    print(r"[leantex] you can now use \usepackage{leantex}")
    print(r"[leantex] installed ~/.latexmkrc auto-hook for LeanTeX")
    return 0


def cmd_latexmk_run(args: argparse.Namespace) -> int:
    engine = args.engine
    engine_args = list(args.engine_args or [])

    tex_arg: str | None = None
    for tok in reversed(engine_args):
        if tok.lower().endswith(".tex"):
            tex_arg = tok
            break
    if tex_arg is None:
        for tok in reversed(engine_args):
            if not tok.startswith("-"):
                tex_arg = tok
                break

    if tex_arg is not None:
        tex_path = Path(tex_arg).resolve()
        if tex_path.exists() and _tex_uses_leantex(tex_path):
            build_cmd = [
                sys.executable,
                "-m",
                "leantex",
                "build",
                str(tex_path),
                "--no-latexmk",
            ]
            proc_build = subprocess.run(build_cmd)
            if proc_build.returncode != 0:
                return proc_build.returncode

    proc_engine = subprocess.run([engine, *engine_args])
    return proc_engine.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leantex")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="parse TeX, run Lean, generate include file, optionally run latexmk")
    p_build.add_argument("tex_path", help="path to .tex file")
    p_build.add_argument("--no-latexmk", action="store_true", help="skip latexmk")
    p_build.add_argument("--project-root", help="optional Lean/Lake project root override")
    p_build.set_defaults(func=cmd_build)

    p_watch = sub.add_parser("watch", help="watch TeX file and rebuild on change")
    p_watch.add_argument("tex_path", help="path to .tex file")
    p_watch.add_argument("--interval", type=float, default=1.0, help="poll interval in seconds")
    p_watch.add_argument("--no-latexmk", action="store_true", help="skip latexmk")
    p_watch.add_argument("--project-root", help="optional Lean/Lake project root override")
    p_watch.set_defaults(func=cmd_watch)

    p_install = sub.add_parser("install-tex", help="install leantex.sty into TEXMFHOME")
    p_install.add_argument("--dest", help="optional TEXMF root override (default: TEXMFHOME)")
    p_install.set_defaults(func=cmd_install_tex)

    p_latexmk = sub.add_parser(
        "latexmk-run",
        help=argparse.SUPPRESS,
    )
    p_latexmk.add_argument("engine", choices=["pdflatex", "xelatex", "lualatex"])
    p_latexmk.add_argument("engine_args", nargs=argparse.REMAINDER)
    p_latexmk.set_defaults(func=cmd_latexmk_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
