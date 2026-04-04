"""Render pipeline for LeanTeX v2 (minted-based).

v2 always uses raw UTF-8 files -- no U+XXXX sanitization is needed since
minted/pygments handles Unicode natively via XeLaTeX/LuaLaTeX.
"""

from __future__ import annotations

import re
from pathlib import Path

from .io_utils import write_text_if_changed
from .models import LeanMessage, Snippet


def _safe_text_for_file(text: str) -> str:
    return text.rstrip("\n") + "\n" if text else ""


def _severity_rank(sev: str) -> int:
    if sev == "error":
        return 0
    if sev == "warning":
        return 1
    return 2


def _clean_text(msg: LeanMessage) -> str:
    """Strip internal prefixes from a message's text."""
    text = msg.text
    # Remove "[infoview] tactic state:\n" prefix
    text = re.sub(r"^\[infoview\] tactic state:\s*\n?", "", text)
    # Remove "[infoview message] " prefix
    text = re.sub(r"^\[infoview message\] ", "", text)
    return text.strip()


def format_messages_v2(
    messages: list[LeanMessage],
    infoview_mode: str = "auto",
    infoview_lines: int = 4,
) -> str:
    """Format Lean messages for clean PDF output (no internal metadata)."""
    if not messages:
        return ""

    # Deduplicate
    deduped: list[LeanMessage] = []
    seen: set[tuple[str, int | None, int | None, str, str]] = set()
    for msg in messages:
        key = (msg.severity, msg.line, msg.col, msg.text, msg.source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(msg)

    # Categorize
    lean_msgs = [m for m in deduped if m.source not in {"infoview", "infoview-message"}]
    infoview_state = [m for m in deduped if m.source == "infoview"]
    infoview_tab = [m for m in deduped if m.source == "infoview-message"]

    # Normalize whitespace for comparison (multiline vs single-line duplicates)
    def _norm(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    # Deduplicate infoview-message entries that duplicate lean_msgs content
    lean_norm_keys = {(m.severity, _norm(_clean_text(m))) for m in lean_msgs}
    infoview_tab = [
        m for m in infoview_tab
        if (m.severity, _norm(_clean_text(m))) not in lean_norm_keys
    ]

    # Also deduplicate infoview_tab entries whose cleaned text duplicates
    # cleaned infoview_state text (e.g. "no goals" vs "Goals accomplished!")
    state_texts = {_norm(_clean_text(m)) for m in infoview_state}

    # Build clean output lines
    output_parts: list[str] = []

    # Lean messages (errors first, then warnings, then info)
    for msg in sorted(lean_msgs, key=lambda m: (_severity_rank(m.severity), m.line or 10**9)):
        text = _clean_text(msg)
        if msg.severity == "error":
            output_parts.append(f"error: {text}")
        elif msg.severity == "warning":
            output_parts.append(f"warning: {text}")
        else:
            output_parts.append(text)

    # Infoview state (tactic goals)
    for msg in sorted(infoview_state, key=lambda m: (m.line or 10**9,)):
        text = _clean_text(msg)
        if text and text.lower() not in {"no goals"}:
            # Show tactic state (goal hypotheses and target)
            output_parts.append(text)
        elif text.lower() == "no goals":
            # Only show "no goals" if there are no "Goals accomplished!" messages
            has_accomplished = any("goals accomplished" in _clean_text(m).lower() for m in infoview_tab)
            if not has_accomplished:
                output_parts.append(text)

    # Infoview messages (Goals accomplished!, etc.)
    for msg in sorted(infoview_tab, key=lambda m: (_severity_rank(m.severity), m.line or 10**9)):
        text = _clean_text(msg)
        if _norm(text) in state_texts:
            continue
        if msg.severity == "error":
            output_parts.append(f"error: {text}")
        elif msg.severity == "warning":
            output_parts.append(f"warning: {text}")
        else:
            output_parts.append(text)

    if not output_parts:
        return ""

    return "\n".join(output_parts)


def write_generated_assets_v2(
    generated_tex_path: Path,
    snippets_dir: Path,
    snippets: list[Snippet],
    snippet_messages: dict[int, list[LeanMessage]],
    document_messages: list[LeanMessage] | None = None,
) -> None:
    """Write v2 generated assets: raw UTF-8 files + leantexv2.generated.tex."""
    snippets_dir.mkdir(parents=True, exist_ok=True)
    generated_tex_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts_dir = snippets_dir.parent

    lines: list[str] = [
        "% LeanTeX v2 generated file. Do not edit manually.",
        r"\expandafter\gdef\csname leantex@generatedloaded\endcsname{1}",
        "",
    ]
    block_lines: list[str] = []

    for snip in snippets:
        # v2 only writes raw UTF-8 files (no sanitized versions needed)
        code_raw_file = snippets_dir / f"snippet_{snip.index:03}.code.raw.lean"
        out_raw_file = snippets_dir / f"snippet_{snip.index:03}.out.raw.txt"
        snip_msgs = snippet_messages.get(snip.index, [])

        write_text_if_changed(
            code_raw_file,
            _safe_text_for_file(snip.code),
            encoding="utf-8",
        )
        output_text = format_messages_v2(
            snip_msgs,
            infoview_mode=snip.infoview,
            infoview_lines=snip.infoview_lines,
        )
        write_text_if_changed(
            out_raw_file,
            _safe_text_for_file(output_text),
            encoding="utf-8",
        )

        has_error = any(m.severity == "error" for m in snip_msgs)

        # v2 generated tex only needs raw paths (no sanitized paths, no literate mappings)
        block_lines.append(
            f"\\expandafter\\gdef\\csname leantex@show@{snip.index}\\endcsname{{{snip.show}}}"
        )
        # Still write codepath for compatibility with the loader detection
        block_lines.append(
            f"\\expandafter\\gdef\\csname leantex@codepath@{snip.index}\\endcsname"
            f"{{{code_raw_file.as_posix()}}}"
        )
        block_lines.append(
            f"\\expandafter\\gdef\\csname leantex@coderawpath@{snip.index}\\endcsname"
            f"{{{code_raw_file.as_posix()}}}"
        )
        block_lines.append(
            f"\\expandafter\\gdef\\csname leantex@outrawpath@{snip.index}\\endcsname"
            f"{{{out_raw_file.as_posix()}}}"
        )
        block_lines.append(
            f"\\expandafter\\gdef\\csname leantex@haserror@{snip.index}\\endcsname"
            f"{{{1 if has_error else 0}}}"
        )
        if snip.name:
            block_lines.append(
                f"\\expandafter\\gdef\\csname leantex@name@{snip.index}\\endcsname{{{snip.name}}}"
            )
        if snip.code_size:
            block_lines.append(
                f"\\expandafter\\gdef\\csname leantex@codesize@{snip.index}\\endcsname{{{snip.code_size}}}"
            )
        if snip.output_size:
            block_lines.append(
                f"\\expandafter\\gdef\\csname leantex@outsize@{snip.index}\\endcsname{{{snip.output_size}}}"
            )
        block_lines.append("")

    # Document-level extracted infoview
    extracted_out_raw_file = artifacts_dir / "extracted.infoview.raw.txt"
    extracted_output_text = format_messages_v2(
        document_messages or [], infoview_mode="full"
    )
    write_text_if_changed(
        extracted_out_raw_file,
        _safe_text_for_file(extracted_output_text),
        encoding="utf-8",
    )
    extracted_has_error = any(
        m.severity == "error" for m in (document_messages or [])
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
