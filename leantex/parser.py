from __future__ import annotations

import re
from pathlib import Path

from .models import Snippet

BEGIN_RE = re.compile(r"\\begin\{lean\}(?:\[(?P<opts>[^\]]*)\])?")
END_RE = re.compile(r"\\end\{lean\}")
MINTED_BEGIN_RE = re.compile(
    r"\\begin\{minted\}(?:\[(?P<opts>[^\]]*)\])?\{(?P<lang>[^\}]*)\}"
)
MINTED_END_RE = re.compile(r"\\end\{minted\}")
LEANTEX_MACRO_RE = re.compile(r"\\leantex(?![A-Za-z@])(?:\[(?P<opts>[^\]]*)\])?")
LEANTEX_CONFIG_RE = re.compile(
    r"\\leantexconfig(?:ure)?\s*\{(?P<name>[^\}]*)\}\s*\{(?P<opts>[^\}]*)\}"
)
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


def _strip_name_braces(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = _strip_outer_braces(raw)
    return value or None


def _snippet_from_parts(
    index: int,
    code: str,
    start_line: int,
    end_line: int,
    opts: dict[str, str],
    *,
    default_show: str,
    source: str,
) -> Snippet:
    infoview_mode, infoview_lines = _parse_infoview_mode(opts)
    name = _strip_name_braces(
        opts.get("name") or opts.get("label") or opts.get("id")
    )
    return Snippet(
        index=index,
        code=code.strip("\n"),
        start_line=start_line,
        end_line=end_line,
        name=name,
        show=opts.get("show", default_show),
        pp=opts.get("pp"),
        infoview=infoview_mode,
        infoview_lines=infoview_lines,
        code_size=_parse_code_size(opts),
        output_size=_parse_output_size(opts),
        source=source,
    )


def _find_balanced_brace_end(text: str, open_idx: int) -> int | None:
    depth = 0
    escaped = False
    for idx in range(open_idx, len(text)):
        ch = text[idx]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return idx
    return None


def _parse_leantex_macro_at(
    text: str,
    match: re.Match[str],
) -> tuple[str, int] | None:
    pos = match.end()
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text) or text[pos] != "{":
        return None
    end = _find_balanced_brace_end(text, pos)
    if end is None:
        return None
    return text[pos + 1 : end], end + 1


def parse_tex_for_lean(tex_path: Path, *, include_minted: bool = False) -> list[Snippet]:
    snippets: list[Snippet] = []
    lines = tex_path.read_text(encoding="utf-8").splitlines()
    full_text = tex_path.read_text(encoding="utf-8")
    named_configs: dict[str, dict[str, str]] = {}
    for config in LEANTEX_CONFIG_RE.finditer(full_text):
        name = _strip_name_braces(config.group("name"))
        if name:
            named_configs[name] = parse_keyvals(config.group("opts"))

    consumed_macro_lines: set[int] = set()
    for macro in LEANTEX_MACRO_RE.finditer(full_text):
        parsed = _parse_leantex_macro_at(full_text, macro)
        if parsed is None:
            continue
        code, end_pos = parsed
        start_line = full_text.count("\n", 0, macro.start()) + 1
        end_line = full_text.count("\n", 0, end_pos) + 1
        consumed_macro_lines.update(range(start_line, end_line + 1))
        opts = parse_keyvals(macro.group("opts"))
        snippets.append(
            _snippet_from_parts(
                len(snippets) + 1,
                code,
                start_line,
                end_line,
                opts,
                default_show="output",
                source="macro",
            )
        )

    i = 0
    in_snippet = False
    snippet_start = 0
    snippet_lines: list[str] = []
    snippet_opts: dict[str, str] = {}
    snippet_source = "lean"
    current_end_re = END_RE
    current_default_show = "both"

    while i < len(lines):
        line = lines[i]
        line_no = i + 1
        if line_no in consumed_macro_lines:
            i += 1
            continue
        if not in_snippet:
            candidate = _strip_comment(line)
            begin = BEGIN_RE.search(candidate)
            minted_begin = None
            if include_minted:
                minted_begin = MINTED_BEGIN_RE.search(candidate)
                if minted_begin:
                    lang = minted_begin.group("lang").strip().lower()
                    if lang not in {"lean", "lean4"}:
                        minted_begin = None
            if begin is None and minted_begin is not None:
                begin = minted_begin
            if begin:
                in_snippet = True
                snippet_start = i + 1
                snippet_lines = []
                snippet_opts = parse_keyvals(begin.group("opts"))
                snippet_source = "minted" if begin is minted_begin else "lean"
                if snippet_source == "minted":
                    name = _strip_name_braces(
                        snippet_opts.get("name")
                        or snippet_opts.get("label")
                        or snippet_opts.get("id")
                    )
                    if name in named_configs:
                        snippet_opts = {**snippet_opts, **named_configs[name]}
                current_end_re = MINTED_END_RE if snippet_source == "minted" else END_RE
                current_default_show = "output" if snippet_source == "minted" else "both"

                tail = candidate[begin.end() :]
                end_here = current_end_re.search(tail)
                if end_here:
                    snippet_lines.append(tail[: end_here.start()])
                    snippets.append(
                        _snippet_from_parts(
                            len(snippets) + 1,
                            "\n".join(snippet_lines),
                            snippet_start,
                            i + 1,
                            snippet_opts,
                            default_show=current_default_show,
                            source=snippet_source,
                        )
                    )
                    in_snippet = False
                else:
                    if tail:
                        snippet_lines.append(tail)
            i += 1
            continue

        candidate = _strip_comment(line)
        end = current_end_re.search(candidate)
        if end:
            snippet_lines.append(candidate[: end.start()])
            snippets.append(
                _snippet_from_parts(
                    len(snippets) + 1,
                    "\n".join(snippet_lines),
                    snippet_start,
                    i + 1,
                    snippet_opts,
                    default_show=current_default_show,
                    source=snippet_source,
                )
            )
            in_snippet = False
            snippet_lines = []
            snippet_opts = {}
            snippet_source = "lean"
            current_end_re = END_RE
            current_default_show = "both"
        else:
            snippet_lines.append(line)
        i += 1

    if in_snippet:
        raise ValueError(f"Unclosed lean environment in {tex_path} starting at line {snippet_start}")

    ordered: list[Snippet] = []
    for new_index, snip in enumerate(
        sorted(snippets, key=lambda s: (s.start_line, s.end_line, s.source)),
        start=1,
    ):
        snip.index = new_index
        ordered.append(snip)

    return ordered


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
            if (
                "leantexonefile" in packages
                or "leantexv2onefile" in packages
            ):
                shared_context = True
            if (
                "leantex" in packages
                or "leantexv2" in packages
            ) and "onefile" in opts:
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
    """Return True if the document uses leantexv2/v2.5 (minted-based) rather than v1."""
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
