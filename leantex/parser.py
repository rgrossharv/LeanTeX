from __future__ import annotations

import re
from pathlib import Path

from .models import Snippet

BEGIN_RE = re.compile(r"\\begin\{lean\}(?:\[(?P<opts>[^\]]*)\])?")
END_RE = re.compile(r"\\end\{lean\}")
USEPACKAGE_RE = re.compile(
    r"\\usepackage\s*(?:\[(?P<opts>[^\]]*)\])?\s*\{(?P<pkg>[^\}]*)\}"
)
ONEFILE_ENABLE_RE = re.compile(
    r"\\(?:leantexenableonefile|leantexonefiletrue)\b"
)
ONEFILE_DISABLE_RE = re.compile(
    r"\\(?:leantexdisableonefile|leantexonefilefalse)\b"
)
INFOVIEW_MODES = {"auto", "full", "goals", "lines"}
CODE_SIZE_MAP = {
    "tiny": r"\tiny",
    "scriptsize": r"\scriptsize",
    "footnotesize": r"\footnotesize",
    "small": r"\small",
    "normalsize": r"\normalsize",
    "large": r"\large",
    "huge": r"\huge",
}


def _strip_comment(line: str) -> str:
    idx = line.find("%")
    if idx == -1:
        return line
    return line[:idx]


def parse_keyvals(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    out: dict[str, str] = {}
    for part in raw.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            out[key.strip()] = value.strip()
        else:
            out[chunk] = "true"
    return out


def _parse_positive_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        n = int(raw.strip())
    except (TypeError, ValueError):
        return default
    if n <= 0:
        return default
    return n


def _parse_infoview_mode(opts: dict[str, str]) -> tuple[str, int]:
    raw_mode = opts.get("infoview", "auto").strip().lower()
    lines = _parse_positive_int(opts.get("ivlines"), default=4)

    if raw_mode.startswith("lines:"):
        raw_limit = raw_mode.split(":", 1)[1].strip()
        lines = _parse_positive_int(raw_limit, default=lines)
        raw_mode = "lines"
    elif raw_mode.startswith("lines(") and raw_mode.endswith(")"):
        raw_limit = raw_mode[6:-1].strip()
        lines = _parse_positive_int(raw_limit, default=lines)
        raw_mode = "lines"

    if raw_mode not in INFOVIEW_MODES:
        raw_mode = "auto"

    return raw_mode, lines


def _strip_outer_braces(value: str) -> str:
    out = value.strip()
    while len(out) >= 2 and out.startswith("{") and out.endswith("}"):
        out = out[1:-1].strip()
    return out


def _normalize_size_command(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = _strip_outer_braces(raw)
    if not value:
        return None
    if value.startswith("\\"):
        return value
    lowered = value.lower()
    if lowered in CODE_SIZE_MAP:
        return CODE_SIZE_MAP[lowered]
    if re.fullmatch(r"[A-Za-z@]+", value):
        return "\\" + value
    return None


def _parse_code_size(opts: dict[str, str]) -> str | None:
    text_size = _normalize_size_command(opts.get("textsize") or opts.get("size"))
    return _normalize_size_command(opts.get("codesize")) or text_size


def _parse_output_size(opts: dict[str, str]) -> str | None:
    text_size = _normalize_size_command(opts.get("textsize") or opts.get("size"))
    return _normalize_size_command(
        opts.get("outsize") or opts.get("outputsize")
    ) or text_size


def parse_tex_for_lean(tex_path: Path) -> list[Snippet]:
    snippets: list[Snippet] = []
    lines = tex_path.read_text(encoding="utf-8").splitlines()

    i = 0
    in_snippet = False
    snippet_start = 0
    snippet_lines: list[str] = []
    snippet_opts: dict[str, str] = {}

    while i < len(lines):
        line = lines[i]
        if not in_snippet:
            candidate = _strip_comment(line)
            begin = BEGIN_RE.search(candidate)
            if begin:
                in_snippet = True
                snippet_start = i + 1
                snippet_lines = []
                snippet_opts = parse_keyvals(begin.group("opts"))

                tail = candidate[begin.end() :]
                end_here = END_RE.search(tail)
                if end_here:
                    infoview_mode, infoview_lines = _parse_infoview_mode(snippet_opts)
                    snippet_lines.append(tail[: end_here.start()])
                    snippets.append(
                        Snippet(
                            index=len(snippets) + 1,
                            code="\n".join(snippet_lines).strip("\n"),
                            start_line=snippet_start,
                            end_line=i + 1,
                            name=snippet_opts.get("name"),
                            show=snippet_opts.get("show", "both"),
                            pp=snippet_opts.get("pp"),
                            infoview=infoview_mode,
                            infoview_lines=infoview_lines,
                            code_size=_parse_code_size(snippet_opts),
                            output_size=_parse_output_size(snippet_opts),
                        )
                    )
                    in_snippet = False
                else:
                    if tail:
                        snippet_lines.append(tail)
            i += 1
            continue

        candidate = _strip_comment(line)
        end = END_RE.search(candidate)
        if end:
            infoview_mode, infoview_lines = _parse_infoview_mode(snippet_opts)
            snippet_lines.append(candidate[: end.start()])
            snippets.append(
                Snippet(
                    index=len(snippets) + 1,
                    code="\n".join(snippet_lines).strip("\n"),
                    start_line=snippet_start,
                    end_line=i + 1,
                    name=snippet_opts.get("name"),
                    show=snippet_opts.get("show", "both"),
                    pp=snippet_opts.get("pp"),
                    infoview=infoview_mode,
                    infoview_lines=infoview_lines,
                    code_size=_parse_code_size(snippet_opts),
                    output_size=_parse_output_size(snippet_opts),
                )
            )
            in_snippet = False
            snippet_lines = []
            snippet_opts = {}
        else:
            snippet_lines.append(line)
        i += 1

    if in_snippet:
        raise ValueError(f"Unclosed lean environment in {tex_path} starting at line {snippet_start}")

    return snippets


def detect_shared_context_mode(tex_path: Path) -> bool:
    lines = tex_path.read_text(encoding="utf-8").splitlines()
    shared_context = False

    for raw_line in lines:
        line = _strip_comment(raw_line)
        if not line.strip():
            continue

        for m in USEPACKAGE_RE.finditer(line):
            packages = [p.strip() for p in m.group("pkg").split(",") if p.strip()]
            opts = parse_keyvals(m.group("opts"))
            if "leantexonefile" in packages or "leantexv2onefile" in packages:
                shared_context = True
            if ("leantex" in packages or "leantexv2" in packages) and "onefile" in opts:
                value = opts.get("onefile", "true").strip().lower()
                if value in {"false", "0", "off", "no"}:
                    shared_context = False
                else:
                    shared_context = True

        if ONEFILE_ENABLE_RE.search(line):
            shared_context = True
        if ONEFILE_DISABLE_RE.search(line):
            shared_context = False

    return shared_context


def detect_v2_mode(tex_path: Path) -> bool:
    """Return True if the document uses leantexv2 (minted-based) rather than v1."""
    lines = tex_path.read_text(encoding="utf-8").splitlines()
    for raw_line in lines:
        line = _strip_comment(raw_line)
        if not line.strip():
            continue
        for m in USEPACKAGE_RE.finditer(line):
            packages = [p.strip() for p in m.group("pkg").split(",") if p.strip()]
            if "leantexv2" in packages or "leantexv2onefile" in packages:
                return True
    return False
