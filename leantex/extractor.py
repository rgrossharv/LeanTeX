from __future__ import annotations

import re
from pathlib import Path

from .io_utils import write_text_if_changed
from .models import ExtractedLean, Snippet, SnippetRange

IMPORT_RE = re.compile(r"^\s*import\s+\S")


def _is_import_line(line: str) -> bool:
    stripped = line.lstrip()
    if stripped.startswith("--"):
        return False
    return bool(IMPORT_RE.match(line))


def _collect_hoisted_imports(snippets: list[Snippet]) -> list[str]:
    seen: set[str] = set()
    imports: list[str] = []
    for snip in snippets:
        for line in snip.code.splitlines():
            if _is_import_line(line):
                stmt = line.strip()
                if stmt not in seen:
                    seen.add(stmt)
                    imports.append(stmt)
    return imports


def write_extracted_lean(
    path: Path,
    snippets: list[Snippet],
    shared_context: bool = False,
) -> ExtractedLean:
    ranges: list[SnippetRange] = []
    hoisted_import_line_to_stmt: dict[int, str] = {}
    hoisted_imports = _collect_hoisted_imports(snippets)

    lines: list[str] = [
        "-- LeanTeX generated file. Do not edit manually.",
        "",
    ]
    if hoisted_imports:
        for stmt in hoisted_imports:
            lines.append(stmt)
            hoisted_import_line_to_stmt[len(lines)] = stmt
        lines.append("")

    current_line = len(lines) + 1

    for snip in snippets:
        lines.append(f"-- BEGIN_SNIPPET {snip.index}")
        current_line += 1
        if not shared_context:
            lines.append(f"namespace LeanTeX_Snippet_{snip.index}")
            current_line += 1

        start = current_line

        raw_lines = snip.code.splitlines() if snip.code else [""]
        code_lines: list[str] = []
        for raw in raw_lines:
            if _is_import_line(raw):
                # Keep line accounting stable while moving imports to file top.
                code_lines.append(f"-- LeanTeX hoisted import: {raw.strip()}")
            else:
                code_lines.append(raw)
        lines.extend(code_lines)
        current_line += len(code_lines)

        end = current_line - 1
        if not shared_context:
            lines.append(f"end LeanTeX_Snippet_{snip.index}")
            current_line += 1
        lines.append(f"-- END_SNIPPET {snip.index}")
        lines.append("")
        current_line += 2

        ranges.append(SnippetRange(index=snip.index, start_line=start, end_line=end))

    write_text_if_changed(path, "\n".join(lines), encoding="utf-8")
    return ExtractedLean(
        ranges=ranges,
        hoisted_import_line_to_stmt=hoisted_import_line_to_stmt,
    )
