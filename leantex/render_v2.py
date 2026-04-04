"""Render pipeline for LeanTeX v2 (minted-based).

v2 always uses raw UTF-8 files -- no U+XXXX sanitization is needed since
minted/pygments handles Unicode natively via XeLaTeX/LuaLaTeX.
"""

from __future__ import annotations

import re
from pathlib import Path

from .io_utils import write_text_if_changed
from .models import LeanMessage, Snippet
from .render import format_messages


def _safe_text_for_file(text: str) -> str:
    return text.rstrip("\n") + "\n" if text else ""


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
        output_text = format_messages(
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
        has_output = bool(output_text.strip())

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
        block_lines.append(
            f"\\expandafter\\gdef\\csname leantex@hasoutput@{snip.index}\\endcsname"
            f"{{{1 if has_output else 0}}}"
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
    extracted_output_text = format_messages(
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
    extracted_has_output = bool(extracted_output_text.strip())

    lines.append(
        "\\expandafter\\gdef\\csname leantex@extractedoutrawpath\\endcsname"
        f"{{{extracted_out_raw_file.as_posix()}}}"
    )
    lines.append(
        "\\expandafter\\gdef\\csname leantex@extractedhaserror\\endcsname"
        f"{{{1 if extracted_has_error else 0}}}"
    )
    lines.append(
        "\\expandafter\\gdef\\csname leantex@extractedhasoutput\\endcsname"
        f"{{{1 if extracted_has_output else 0}}}"
    )
    lines.append("")

    lines.extend(block_lines)

    write_text_if_changed(generated_tex_path, "\n".join(lines), encoding="utf-8")
