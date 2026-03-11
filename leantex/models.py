from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Snippet:
    index: int
    code: str
    start_line: int
    end_line: int
    name: Optional[str] = None
    show: str = "both"
    pp: Optional[str] = None
    infoview: str = "auto"
    infoview_lines: int = 4
    code_size: Optional[str] = None
    output_size: Optional[str] = None


@dataclass
class SnippetRange:
    index: int
    start_line: int
    end_line: int


@dataclass
class ExtractedLean:
    ranges: list[SnippetRange]
    hoisted_import_line_to_stmt: dict[int, str] = field(default_factory=dict)


@dataclass
class LeanMessage:
    severity: str
    text: str
    line: Optional[int] = None
    col: Optional[int] = None
    end_line: Optional[int] = None
    end_col: Optional[int] = None
    source: str = "lean"


@dataclass
class BuildContext:
    tex_path: Path
    tex_dir: Path
    project_root: Path
    generated_dir: Path
    extracted_lean_path: Path
    generated_tex_path: Path
    snippets_dir: Path
    output_dir: Path


@dataclass
class BuildResult:
    snippets: list[Snippet]
    snippet_messages: dict[int, list[LeanMessage]] = field(default_factory=dict)
    document_messages: list[LeanMessage] = field(default_factory=list)
    global_messages: list[LeanMessage] = field(default_factory=list)
    raw_output: str = ""
