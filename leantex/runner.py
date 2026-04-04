from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .models import LeanMessage

PLAIN_DIAG_RE = re.compile(
    r"^(?P<file>.*?):(?P<line>\d+):(?P<col>\d+):\s*(?P<severity>error|warning|info):\s*(?P<msg>.*)$"
)


class LeanToolMissingError(RuntimeError):
    pass


def _normalize_severity(raw: str) -> str:
    lower = raw.lower()
    if lower.startswith("err"):
        return "error"
    if lower.startswith("warn"):
        return "warning"
    if lower.startswith("info"):
        return "info"
    if lower.startswith("information"):
        return "info"
    return "info"


def _normalize_column(col: object) -> int | None:
    if not isinstance(col, int):
        return None
    return 1 if col <= 0 else col


def _parse_json_events(text: str) -> list[LeanMessage]:
    out: list[LeanMessage] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        severity = event.get("severity")
        msg = event.get("message") or event.get("data")
        if severity and msg:
            pos = event.get("pos") or {}
            end_pos = event.get("endPos") or {}
            out.append(
                LeanMessage(
                    severity=_normalize_severity(severity),
                    text=str(msg).strip(),
                    line=pos.get("line"),
                    col=_normalize_column(pos.get("column")),
                    end_line=end_pos.get("line"),
                    end_col=_normalize_column(end_pos.get("column")),
                    source="json",
                )
            )
            continue

        # Some Lean versions emit a container with nested messages.
        for nested in event.get("messages", []):
            nsev = nested.get("severity")
            nmsg = nested.get("data") or nested.get("message")
            if not (nsev and nmsg):
                continue
            pos = nested.get("pos") or {}
            end_pos = nested.get("endPos") or {}
            out.append(
                LeanMessage(
                    severity=_normalize_severity(str(nsev)),
                    text=str(nmsg).strip(),
                    line=pos.get("line"),
                    col=_normalize_column(pos.get("column")),
                    end_line=end_pos.get("line"),
                    end_col=_normalize_column(end_pos.get("column")),
                    source="json-nested",
                )
            )
    return out


def _parse_plain_diagnostics(text: str) -> list[LeanMessage]:
    out: list[LeanMessage] = []
    for line in text.splitlines():
        m = PLAIN_DIAG_RE.match(line.strip())
        if not m:
            continue
        out.append(
            LeanMessage(
                severity=_normalize_severity(m.group("severity")),
                text=m.group("msg").strip(),
                line=int(m.group("line")),
                col=_normalize_column(int(m.group("col"))),
                source="plain",
            )
        )
    return out


def run_lean(project_root: Path, extracted_lean: Path) -> tuple[list[LeanMessage], str]:
    extracted_abs = extracted_lean.resolve()
    project_root = project_root.resolve()
    try:
        lean_target = str(extracted_abs.relative_to(project_root))
    except ValueError:
        lean_target = str(extracted_abs)
    has_lake = (project_root / "lakefile.lean").exists() or (project_root / "lakefile.toml").exists()

    if has_lake:
        if shutil.which("lake") is None:
            raise LeanToolMissingError("`lake` not found. Install Lean 4 + Lake and try again.")
        cmd = ["lake", "env", "lean", "--json", lean_target]
    else:
        if shutil.which("lean") is None:
            raise LeanToolMissingError("`lean` not found. Install Lean 4 and try again.")
        cmd = ["lean", "--json", lean_target]

    proc = subprocess.run(
        cmd,
        cwd=project_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    combined = "\n".join(part for part in [proc.stdout, proc.stderr] if part)

    messages = _parse_json_events(proc.stdout)
    if not messages:
        messages = _parse_json_events(combined)
    if not messages:
        messages = _parse_plain_diagnostics(combined)

    return messages, combined
