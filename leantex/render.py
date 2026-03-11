from __future__ import annotations

import functools
import re
import subprocess
import unicodedata
from pathlib import Path

from .io_utils import write_text_if_changed
from .models import LeanMessage, Snippet

INFOVIEW_STATE_LINE_LIMIT = 4
DECL_HEAD_RE = re.compile(
    r"^\s*(?:(?:private|protected)\s+)?"
    r"(theorem|lemma|example|corollary)\b"
)
CHECKMARK_TOKEN = "U+2713U+2713 "
NO_CHECKMARK_TOKEN = "U+2717U+2717 "
STATIC_LITERATE_CODEPOINTS = {
    "22A2",
    "2192",
    "2190",
    "2194",
    "2200",
    "2203",
    "2227",
    "2228",
    "00AC",
    "22A5",
    "22A4",
    "2264",
    "2265",
    "2260",
    "2208",
    "2209",
    "2286",
    "2282",
    "222A",
    "2229",
    "2218",
    "00B7",
    "2016",
    "2713",
    "2717",
    "27E8",
    "27E9",
    "27EA",
    "27EB",
    "03B1",
    "03B2",
    "03B3",
    "03B4",
    "03B5",
    "03B6",
    "03B7",
    "03B8",
    "03B9",
    "03BA",
    "03BB",
    "03BC",
    "03BD",
    "03BE",
    "03C0",
    "03C1",
    "03C3",
    "03C4",
    "03C5",
    "03C6",
    "03D5",
    "03C7",
    "03C8",
    "03C9",
    "0393",
    "0394",
    "0398",
    "039B",
    "039E",
    "03A0",
    "03A3",
    "03A6",
    "03A8",
    "03A9",
    "2115",
    "2124",
    "211A",
    "211D",
}
UNICODE_MATH_LINE_RE = re.compile(
    r'\\UnicodeMathSymbol\{"([0-9A-F]+)\}\{\\([^}]*)\}\{\\([^}]*)\}'
)
UNICODE_MATH_SAFE_CLASSES = {
    "mathalpha",
    "mathord",
    "mathbin",
    "mathrel",
    "mathopen",
    "mathclose",
    "mathfence",
    "mathpunct",
}
MATH_ALNUM_STYLE_TO_CMD = {
    "BOLD": "mathbf",
    "ITALIC": "mathit",
    "BOLD ITALIC": "boldsymbol",
    "SCRIPT": "mathcal",
    "BOLD SCRIPT": "mathcal",
    "FRAKTUR": "mathfrak",
    "DOUBLE-STRUCK": "mathbb",
    "BOLD FRAKTUR": "mathfrak",
    "SANS-SERIF": "mathsf",
    "SANS-SERIF BOLD": "mathsf",
    "SANS-SERIF ITALIC": "mathsf",
    "SANS-SERIF BOLD ITALIC": "mathsf",
    "MONOSPACE": "mathtt",
}
LETTERLIKE_STYLE_TO_CMD = {
    "DOUBLE-STRUCK": "mathbb",
    "BLACK-LETTER": "mathfrak",
    "SCRIPT": "mathcal",
}


def _sanitize_for_listings(text: str) -> str:
    # Keep source assets ASCII-only for pdflatex/listings stability.
    # Encode non-ASCII points as U+XXXX so style-level literate mappings can render
    # common Lean symbols while unknown points still remain readable.
    out: list[str] = []
    for ch in text:
        if ch == "\n" or ch == "\t":
            out.append(ch)
            continue
        if ord(ch) < 128:
            out.append(ch)
        else:
            out.append(f"U+{ord(ch):04X}")
    return "".join(out)


def _collect_non_ascii_codepoints(text: str) -> set[str]:
    out: set[str] = set()
    for ch in text:
        if ord(ch) >= 128:
            out.add(f"{ord(ch):04X}")
    return out


def _kpsewhich(name: str) -> str | None:
    try:
        proc = subprocess.run(
            ["kpsewhich", name],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    path = proc.stdout.strip()
    return path if path else None


def _normalize_unicode_math_command(raw: str) -> str | None:
    cmd = raw.strip()
    if not cmd:
        return None

    # unicode-math uses "mup*" names for upright greek; map to classic names.
    if cmd.startswith("mup") and len(cmd) > 3:
        cmd = cmd[3:]

    if re.fullmatch(r"[A-Za-z@]+", cmd):
        return cmd
    return None


@functools.lru_cache(maxsize=1)
def _unicode_math_command_map() -> dict[str, str]:
    path = _kpsewhich("unicode-math-table.tex")
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    out: dict[str, str] = {}
    for codepoint, raw_cmd, raw_class in UNICODE_MATH_LINE_RE.findall(text):
        if raw_class.strip() not in UNICODE_MATH_SAFE_CLASSES:
            continue
        cmd = _normalize_unicode_math_command(raw_cmd)
        if cmd is None:
            continue
        norm_cp = codepoint.upper().lstrip("0") or "0"
        out.setdefault(norm_cp, cmd)
    return out


def _math_alnum_expr(codepoint: str) -> str | None:
    cp = int(codepoint, 16)
    ch = chr(cp)
    name = unicodedata.name(ch, "")
    if not name.startswith("MATHEMATICAL "):
        return None

    letter = re.match(
        r"^MATHEMATICAL (.+?) (CAPITAL|SMALL) ([A-Z])$",
        name,
    )
    if letter:
        style, case, ascii_letter = letter.groups()
        cmd = MATH_ALNUM_STYLE_TO_CMD.get(style)
        if cmd is None:
            return None
        glyph = ascii_letter if case == "CAPITAL" else ascii_letter.lower()
        if style == "DOUBLE-STRUCK" and case == "SMALL":
            # pdflatex/AMS fonts do not robustly support \mathbb lowercase letters.
            # Use explicit \Bbbk for the common Lean scalar symbol 𝕜 and safe roman
            # fallback for other lowercase double-struck letters.
            if glyph == "k":
                return r"\ensuremath{\Bbbk}"
            return rf"\ensuremath{{\mathrm{{{glyph}}}}}"
        return rf"\ensuremath{{\{cmd}{{{glyph}}}}}"

    digit = re.match(
        r"^MATHEMATICAL (.+?) DIGIT ([0-9])$",
        name,
    )
    if digit:
        style, d = digit.groups()
        cmd = MATH_ALNUM_STYLE_TO_CMD.get(style)
        if cmd is None:
            return None
        return rf"\ensuremath{{\{cmd}{{{d}}}}}"

    return None


def _letterlike_expr(codepoint: str) -> str | None:
    cp = int(codepoint, 16)
    ch = chr(cp)
    name = unicodedata.name(ch, "")

    m = re.match(r"^(DOUBLE-STRUCK|BLACK-LETTER|SCRIPT)\s+(CAPITAL|SMALL)\s+([A-Z])$", name)
    if not m:
        return None
    style, case, ascii_letter = m.groups()
    cmd = LETTERLIKE_STYLE_TO_CMD.get(style)
    if cmd is None:
        return None
    glyph = ascii_letter if case == "CAPITAL" else ascii_letter.lower()
    return rf"\ensuremath{{\{cmd}{{{glyph}}}}}"


def _name_heuristic_expr(codepoint: str) -> str | None:
    cp = int(codepoint, 16)
    ch = chr(cp)
    name = unicodedata.name(ch, "")
    if not name:
        return None

    exact: dict[str, str] = {
        "BULLET": r"\ensuremath{\bullet}",
        "BULLET OPERATOR": r"\ensuremath{\bullet}",
        "MIDDLE DOT": r"\ensuremath{\cdot}",
        "DOUBLE VERTICAL LINE": r"\ensuremath{\Vert}",
        "LEFT ANGLE BRACKET": r"\ensuremath{\langle}",
        "RIGHT ANGLE BRACKET": r"\ensuremath{\rangle}",
        "MATHEMATICAL LEFT DOUBLE ANGLE BRACKET": r"\ensuremath{\langle\!\langle}",
        "MATHEMATICAL RIGHT DOUBLE ANGLE BRACKET": r"\ensuremath{\rangle\!\rangle}",
    }
    if name in exact:
        return exact[name]

    arrow_exact: dict[str, str] = {
        "LEFTWARDS ARROW": r"\ensuremath{\leftarrow}",
        "RIGHTWARDS ARROW": r"\ensuremath{\rightarrow}",
        "UPWARDS ARROW": r"\ensuremath{\uparrow}",
        "DOWNWARDS ARROW": r"\ensuremath{\downarrow}",
        "LEFT RIGHT ARROW": r"\ensuremath{\leftrightarrow}",
        "LEFTWARDS DOUBLE ARROW": r"\ensuremath{\Leftarrow}",
        "RIGHTWARDS DOUBLE ARROW": r"\ensuremath{\Rightarrow}",
        "LEFT RIGHT DOUBLE ARROW": r"\ensuremath{\Leftrightarrow}",
        "UPWARDS DOUBLE ARROW": r"\ensuremath{\Uparrow}",
        "DOWNWARDS DOUBLE ARROW": r"\ensuremath{\Downarrow}",
    }
    if name in arrow_exact:
        return arrow_exact[name]

    return None


def _latex_expr_for_codepoint(codepoint: str) -> str | None:
    # Prefer robust style reconstruction for mathematical alphanumeric symbols.
    expr = _math_alnum_expr(codepoint)
    if expr is not None:
        return expr
    expr = _letterlike_expr(codepoint)
    if expr is not None:
        return expr
    expr = _name_heuristic_expr(codepoint)
    if expr is not None:
        return expr

    normalized = codepoint.upper().lstrip("0") or "0"
    cmd = _unicode_math_command_map().get(normalized)
    if cmd is None:
        return None
    return rf"\leantexmathcmdor{{{cmd}}}{{{codepoint}}}"


def _safe_text_for_file(text: str) -> str:
    return text.rstrip("\n") + "\n" if text else ""


def _severity_rank(sev: str) -> int:
    if sev == "error":
        return 0
    if sev == "warning":
        return 1
    return 2


def _row_line_count(rows: list[str]) -> int:
    total = 0
    for row in rows:
        parts = row.splitlines()
        total += len(parts) if parts else 1
    return total


def _flatten_rows(rows: list[str]) -> list[str]:
    out: list[str] = []
    for row in rows:
        parts = row.splitlines()
        if parts:
            out.extend(parts)
        else:
            out.append(row)
    return out


def _truncate_lines(lines: list[str], limit: int) -> tuple[list[str], int]:
    if limit <= 0:
        return [], len(lines)
    if len(lines) <= limit:
        return lines, 0
    return lines[:limit], len(lines) - limit


def _goals_accomplished_messages(messages: list[LeanMessage]) -> list[LeanMessage]:
    out: list[LeanMessage] = []
    for msg in messages:
        if "goals accomplished" in msg.text.lower():
            out.append(msg)
    return out


def _normalize_infoview_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized in {"auto", "full", "goals", "lines"}:
        return normalized
    return "auto"


def _declaration_start_lines(code_lines: list[str]) -> list[int]:
    starts: list[int] = []
    for line_no, line in enumerate(code_lines, start=1):
        if DECL_HEAD_RE.match(line):
            starts.append(line_no)
    return starts


def _is_blocking_diagnostic(msg: LeanMessage) -> bool:
    # Infoview state snapshots are not diagnostics.
    if msg.source == "infoview":
        return False
    # Only completely clean declarations (no warnings/errors) get checkmarks.
    return msg.severity in {"error", "warning"}


def _blocking_diagnostic_lines(messages: list[LeanMessage]) -> set[int]:
    out: set[int] = set()
    for msg in messages:
        if not _is_blocking_diagnostic(msg):
            continue
        if msg.line is None:
            continue
        start = max(1, msg.line)
        end = msg.end_line if msg.end_line is not None else msg.line
        if end < start:
            end = start
        for line_no in range(start, end + 1):
            out.add(line_no)
    return out


def _checked_declaration_heads(code_lines: list[str], messages: list[LeanMessage]) -> set[int]:
    starts = _declaration_start_lines(code_lines)
    if not starts:
        return set()
    error_lines = _blocking_diagnostic_lines(messages)
    checked: set[int] = set()
    for idx, start in enumerate(starts):
        end = starts[idx + 1] - 1 if idx + 1 < len(starts) else len(code_lines)
        has_error = any(start <= err_line <= end for err_line in error_lines)
        if not has_error:
            checked.add(start)
    return checked


def _annotate_code_for_display(code: str, messages: list[LeanMessage]) -> str:
    code_lines = code.splitlines() if code else [""]
    checked_heads = _checked_declaration_heads(code_lines, messages)
    out_lines: list[str] = []
    for line_no, line in enumerate(code_lines, start=1):
        marker = CHECKMARK_TOKEN if line_no in checked_heads else NO_CHECKMARK_TOKEN
        out_lines.append(f"{marker}{line}")
    return "\n".join(out_lines)


def format_messages(
    messages: list[LeanMessage],
    infoview_mode: str = "auto",
    infoview_lines: int = INFOVIEW_STATE_LINE_LIMIT,
) -> str:
    if not messages:
        return "(no messages)"
    deduped: list[LeanMessage] = []
    seen: set[tuple[str, int | None, int | None, str, str]] = set()
    for msg in messages:
        key = (msg.severity, msg.line, msg.col, msg.text, msg.source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(msg)

    lean_msgs = [m for m in deduped if m.source not in {"infoview", "infoview-message"}]
    infoview_state = [m for m in deduped if m.source == "infoview"]
    infoview_tab = [m for m in deduped if m.source == "infoview-message"]

    lean_text_keys = {(m.severity, m.text.strip()) for m in lean_msgs}
    infoview_tab = [
        m for m in infoview_tab
        if (m.severity, m.text.replace("[infoview message] ", "", 1).strip()) not in lean_text_keys
    ]

    def _rows(msgs: list[LeanMessage]) -> list[str]:
        rows: list[str] = []
        for msg in sorted(msgs, key=lambda m: (_severity_rank(m.severity), m.line or 10**9, m.col or 10**9)):
            loc = ""
            if msg.line is not None and msg.col is not None:
                loc = f"{msg.line}:{msg.col}: "
            rows.append(f"[{msg.severity}] {loc}{msg.text}")
        return rows

    mode = _normalize_infoview_mode(infoview_mode)
    line_limit = infoview_lines if infoview_lines > 0 else INFOVIEW_STATE_LINE_LIMIT

    chunks: list[str] = []
    if lean_msgs:
        chunks.append("=== Messages ===")
        chunks.extend(_rows(lean_msgs))

    state_rows = _rows(infoview_state)
    goal_rows = _rows(_goals_accomplished_messages(infoview_tab))

    if mode == "full":
        if infoview_state:
            chunks.append("=== Infoview State ===")
            chunks.extend(state_rows)
        if infoview_tab:
            chunks.append("=== Infoview Messages ===")
            chunks.extend(_rows(infoview_tab))
    elif mode == "goals":
        if goal_rows:
            chunks.append("=== Infoview Messages ===")
            chunks.extend(goal_rows)
    elif mode == "lines":
        if infoview_state:
            flattened = _flatten_rows(state_rows)
            visible, hidden = _truncate_lines(flattened, line_limit)
            chunks.append(f"=== Infoview State (first {line_limit} line(s)) ===")
            chunks.extend(visible)
            if hidden > 0:
                chunks.append(f"... ({hidden} more line(s) hidden)")
        if goal_rows:
            chunks.append("=== Infoview Messages ===")
            chunks.extend(goal_rows)
    else:
        collapse_infoview_state = _row_line_count(state_rows) > line_limit
        if infoview_state and not collapse_infoview_state:
            chunks.append("=== Infoview State ===")
            chunks.extend(state_rows)
        if infoview_tab:
            chunks.append("=== Infoview Messages ===")
            chunks.extend(_rows(infoview_tab))
        elif infoview_state and collapse_infoview_state and not lean_msgs:
            # Keep output non-empty if state was suppressed but no messages exist.
            last_state = sorted(
                infoview_state,
                key=lambda m: (_severity_rank(m.severity), m.line or 10**9, m.col or 10**9),
            )[-1]
            chunks.append("=== Infoview State (final) ===")
            chunks.extend(_rows([last_state]))

    if mode == "goals" and not goal_rows and not lean_msgs:
        return "(no goals accomplished message)"

    if not chunks:
        chunks.extend(_rows(deduped))

    return "\n".join(chunks)


def write_generated_assets(
    generated_tex_path: Path,
    snippets_dir: Path,
    snippets: list[Snippet],
    snippet_messages: dict[int, list[LeanMessage]],
    document_messages: list[LeanMessage] | None = None,
) -> None:
    snippets_dir.mkdir(parents=True, exist_ok=True)
    generated_tex_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts_dir = snippets_dir.parent

    lines: list[str] = [
        "% LeanTeX generated file. Do not edit manually.",
        r"\expandafter\gdef\csname leantex@generatedloaded\endcsname{1}",
        "",
    ]
    block_lines: list[str] = []
    dynamic_unicode: set[str] = set()

    for snip in snippets:
        code_file = snippets_dir / f"snippet_{snip.index:03}.code.lean"
        code_raw_file = snippets_dir / f"snippet_{snip.index:03}.code.raw.lean"
        out_file = snippets_dir / f"snippet_{snip.index:03}.out.txt"
        out_raw_file = snippets_dir / f"snippet_{snip.index:03}.out.raw.txt"
        snip_msgs = snippet_messages.get(snip.index, [])

        annotated_code = _annotate_code_for_display(snip.code, snip_msgs)
        dynamic_unicode.update(_collect_non_ascii_codepoints(annotated_code))
        write_text_if_changed(code_raw_file, _safe_text_for_file(annotated_code), encoding="utf-8")
        write_text_if_changed(code_file, _safe_text_for_file(_sanitize_for_listings(annotated_code)), encoding="utf-8")
        output_text = format_messages(
            snip_msgs,
            infoview_mode=snip.infoview,
            infoview_lines=snip.infoview_lines,
        )
        dynamic_unicode.update(_collect_non_ascii_codepoints(output_text))
        write_text_if_changed(out_raw_file, _safe_text_for_file(output_text), encoding="utf-8")
        write_text_if_changed(out_file, _safe_text_for_file(_sanitize_for_listings(output_text)), encoding="utf-8")

        has_error = any(m.severity == "error" for m in snip_msgs)

        block_lines.append(f"\\expandafter\\gdef\\csname leantex@show@{snip.index}\\endcsname{{{snip.show}}}")
        block_lines.append(f"\\expandafter\\gdef\\csname leantex@codepath@{snip.index}\\endcsname{{{code_file.as_posix()}}}")
        block_lines.append(f"\\expandafter\\gdef\\csname leantex@coderawpath@{snip.index}\\endcsname{{{code_raw_file.as_posix()}}}")
        block_lines.append(f"\\expandafter\\gdef\\csname leantex@outpath@{snip.index}\\endcsname{{{out_file.as_posix()}}}")
        block_lines.append(f"\\expandafter\\gdef\\csname leantex@outrawpath@{snip.index}\\endcsname{{{out_raw_file.as_posix()}}}")
        block_lines.append(f"\\expandafter\\gdef\\csname leantex@haserror@{snip.index}\\endcsname{{{1 if has_error else 0}}}")
        if snip.name:
            block_lines.append(f"\\expandafter\\gdef\\csname leantex@name@{snip.index}\\endcsname{{{snip.name}}}")
        if snip.pp:
            block_lines.append(f"\\expandafter\\gdef\\csname leantex@pp@{snip.index}\\endcsname{{{snip.pp}}}")
        if snip.code_size:
            block_lines.append(f"\\expandafter\\gdef\\csname leantex@codesize@{snip.index}\\endcsname{{{snip.code_size}}}")
        if snip.output_size:
            block_lines.append(f"\\expandafter\\gdef\\csname leantex@outsize@{snip.index}\\endcsname{{{snip.output_size}}}")
        block_lines.append("")

    extracted_out_file = artifacts_dir / "extracted.infoview.txt"
    extracted_out_raw_file = artifacts_dir / "extracted.infoview.raw.txt"
    extracted_output_text = format_messages(document_messages or [], infoview_mode="full")
    dynamic_unicode.update(_collect_non_ascii_codepoints(extracted_output_text))
    write_text_if_changed(
        extracted_out_raw_file,
        _safe_text_for_file(extracted_output_text),
        encoding="utf-8",
    )
    write_text_if_changed(
        extracted_out_file,
        _safe_text_for_file(_sanitize_for_listings(extracted_output_text)),
        encoding="utf-8",
    )
    extracted_has_error = any(m.severity == "error" for m in (document_messages or []))

    extra_points = sorted(cp for cp in dynamic_unicode if cp not in STATIC_LITERATE_CODEPOINTS)
    if extra_points:
        lines.append("% Dynamic Unicode mappings (generated from snippet/message content)")
        for cp in extra_points:
            expr = _latex_expr_for_codepoint(cp)
            if expr:
                lines.append(f"\\expandafter\\gdef\\csname leantex@unicode@{cp}\\endcsname{{{expr}}}")
    lines.append("\\leantexsetdynamicliterate{")
    for cp in extra_points:
        entry = "{U+" + cp + "}{{\\leantexunicodemapped{" + cp + "}}}" + str(len(cp) + 2)
        lines.append(f"  {entry}")
    lines.append("}")
    lines.append("")

    lines.append(
        "\\expandafter\\gdef\\csname leantex@extractedoutpath\\endcsname"
        f"{{{extracted_out_file.as_posix()}}}"
    )
    lines.append(
        "\\expandafter\\gdef\\csname leantex@extractedoutrawpath\\endcsname"
        f"{{{extracted_out_raw_file.as_posix()}}}"
    )
    lines.append(
        "\\expandafter\\gdef\\csname leantex@extractedhaserror\\endcsname"
        f"{{{1 if extracted_has_error else 0}}}"
    )
    lines.append("")

    lines.extend(block_lines)

    write_text_if_changed(generated_tex_path, "\n".join(lines), encoding="utf-8")
