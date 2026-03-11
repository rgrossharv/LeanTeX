from __future__ import annotations

import json
import os
import re
import selectors
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .models import LeanMessage, SnippetRange
from .runner import LeanToolMissingError

HEADER_SEP = b"\r\n\r\n"
CONTENT_LEN_RE = re.compile(r"^content-length:\s*(\d+)\s*$", re.IGNORECASE)
FENCED_CODE_RE = re.compile(r"^```[^\n]*\n(?P<body>[\s\S]*?)\n```$", re.MULTILINE)


@dataclass
class GoalSnapshot:
    kind: str
    snippet_line: int
    rendered: str


class LeanLspError(RuntimeError):
    pass


class LspClient:
    def __init__(self, cmd: list[str], cwd: Path) -> None:
        self.proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if self.proc.stdin is None or self.proc.stdout is None:
            raise LeanLspError("failed to initialize lean server stdio")
        self._stdin = self.proc.stdin
        self._stdout = self.proc.stdout
        self._buffer = bytearray()
        self._selector = selectors.DefaultSelector()
        self._selector.register(self._stdout, selectors.EVENT_READ)
        self._next_id = 1

    def _send(self, payload: dict) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        msg = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data
        self._stdin.write(msg)
        self._stdin.flush()

    def _send_response(self, request_id: int | str, result: object | None = None) -> None:
        self._send({"jsonrpc": "2.0", "id": request_id, "result": result})

    def notify(self, method: str, params: object | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _fill_buffer(self, timeout_s: float) -> None:
        events = self._selector.select(timeout_s)
        if not events:
            raise TimeoutError("timed out waiting for lean server response")
        chunk = os.read(self._stdout.fileno(), 8192)
        if not chunk:
            err = ""
            if self.proc.stderr is not None:
                try:
                    err = self.proc.stderr.read().decode("utf-8", errors="replace")
                except Exception:
                    err = ""
            raise LeanLspError(f"lean server closed connection unexpectedly{': ' + err if err else ''}")
        self._buffer.extend(chunk)

    def _read_until(self, marker: bytes, timeout_s: float) -> bytes:
        deadline = time.monotonic() + timeout_s
        while True:
            idx = self._buffer.find(marker)
            if idx != -1:
                out = bytes(self._buffer[: idx + len(marker)])
                del self._buffer[: idx + len(marker)]
                return out
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for lean server header")
            self._fill_buffer(remaining)

    def _read_exact(self, n: int, timeout_s: float) -> bytes:
        deadline = time.monotonic() + timeout_s
        while len(self._buffer) < n:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for lean server body")
            self._fill_buffer(remaining)
        out = bytes(self._buffer[:n])
        del self._buffer[:n]
        return out

    def read_message(self, timeout_s: float = 30.0) -> dict:
        raw_header = self._read_until(HEADER_SEP, timeout_s)
        header = raw_header[: -len(HEADER_SEP)].decode("ascii", errors="replace")

        content_length: int | None = None
        for line in header.split("\r\n"):
            m = CONTENT_LEN_RE.match(line.strip())
            if m:
                content_length = int(m.group(1))
                break
        if content_length is None:
            raise LeanLspError(f"invalid lsp header from lean server: {header!r}")

        body = self._read_exact(content_length, timeout_s)
        try:
            return json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise LeanLspError(f"invalid json from lean server: {exc}") from exc

    def request(self, method: str, params: object, timeout_s: float = 30.0) -> object:
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})

        while True:
            msg = self.read_message(timeout_s=timeout_s)

            # Server-to-client request; respond with null result.
            if "method" in msg and "id" in msg and "result" not in msg and "error" not in msg:
                self._send_response(msg["id"], None)
                continue

            if msg.get("id") != request_id:
                continue

            if "error" in msg:
                raise LeanLspError(f"{method} failed: {msg['error']}")
            return msg.get("result")

    def close(self) -> None:
        if self.proc.poll() is not None:
            return
        try:
            try:
                self.request("shutdown", None, timeout_s=5.0)
            except Exception:
                pass
            self.notify("exit", None)
        finally:
            try:
                if self._stdin:
                    self._stdin.close()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=5.0)
            except Exception:
                self.proc.kill()
            self._selector.close()

    def __enter__(self) -> LspClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _strip_markdown_fence(rendered: str) -> str:
    text = rendered.strip()
    m = FENCED_CODE_RE.match(text)
    if m:
        return m.group("body").strip()
    return text


def _candidate_chars_for_goal(line_text: str) -> list[int]:
    n = len(line_text)
    # End-of-line tends to match editor infoview cursor behavior for completed proofs.
    candidates = [max(0, n - 1), n, min(2, n), 0]
    out: list[int] = []
    for c in candidates:
        if c not in out:
            out.append(c)
    return out


def _candidate_chars_for_term(line_text: str) -> list[int]:
    n = len(line_text)
    # Prefer start-of-line for expected type, then broader fallbacks.
    candidates = [0, min(2, n), max(0, n - 1), n]
    out: list[int] = []
    for c in candidates:
        if c not in out:
            out.append(c)
    return out


def _severity_from_lsp_number(severity: object) -> str:
    # LSP DiagnosticSeverity: 1=Error, 2=Warning, 3=Information, 4=Hint
    if severity == 1:
        return "error"
    if severity == 2:
        return "warning"
    return "info"


def _flatten_interactive_message(node: object) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, (int, float, bool)):
        return str(node)
    if isinstance(node, list):
        return "".join(_flatten_interactive_message(part) for part in node)
    if isinstance(node, dict):
        if "text" in node and isinstance(node["text"], str):
            return node["text"]
        if "append" in node and isinstance(node["append"], list):
            return "".join(_flatten_interactive_message(part) for part in node["append"])
        if "tag" in node and isinstance(node["tag"], list):
            return "".join(_flatten_interactive_message(part) for part in node["tag"])
        if "expr" in node:
            return _flatten_interactive_message(node["expr"])
        if "goal" in node:
            return _flatten_interactive_message(node["goal"])
        # Unrecognized metadata nodes (e.g. info references) should not leak into text.
        return ""
    return ""


def _collect_rpc_message_tab(
    lsp: LspClient,
    uri: str,
    lines: list[str],
    snippet_range: SnippetRange,
    session_id: object,
    shared_context: bool = False,
) -> list[LeanMessage]:
    if session_id is None:
        return []
    if not lines or snippet_range.end_line < 1:
        return []

    if shared_context:
        cursor_line = snippet_range.end_line + 1
        cursor_char = 0
    else:
        cursor_line = snippet_range.end_line
        cursor_char = len(lines[snippet_range.end_line - 1])
    if cursor_line < 1:
        cursor_line = 1
    if cursor_line > len(lines):
        cursor_line = len(lines)

    try:
        result = lsp.request(
            "$/lean/rpc/call",
            {
                "textDocument": {"uri": uri},
                "position": {"line": cursor_line - 1, "character": cursor_char},
                "sessionId": session_id,
                "method": "Lean.Widget.getInteractiveDiagnostics",
                "params": {"lineRange?": None},
            },
            timeout_s=30.0,
        )
    except Exception:
        return []

    if not isinstance(result, list):
        return []

    # Keep at most one message per (severity,text), preferring the latest line.
    dedup: dict[tuple[str, str], int] = {}

    for diag in result:
        if not isinstance(diag, dict):
            continue
        start_line0 = (
            (diag.get("range") or {})
            .get("start", {})
            .get("line")
        )
        if not isinstance(start_line0, int):
            continue
        global_line = start_line0 + 1
        if not (snippet_range.start_line <= global_line <= snippet_range.end_line):
            continue

        text = _flatten_interactive_message(diag.get("message")).strip()
        if not text:
            continue
        # Compact accidental whitespace from tagged fragments.
        text = " ".join(text.split())
        if not text:
            continue
        severity = _severity_from_lsp_number(diag.get("severity"))
        local_line = global_line - snippet_range.start_line + 1
        dedup[(severity, text)] = max(dedup.get((severity, text), 0), local_line)

    out: list[LeanMessage] = []
    for (severity, text), local_line in sorted(dedup.items(), key=lambda item: item[1]):
        out.append(
            LeanMessage(
                severity=severity,
                line=local_line,
                col=1,
                text=f"[infoview message] {text}",
                source="infoview-message",
            )
        )
    return out


def _dedupe_goal_snapshots(snapshots: list[GoalSnapshot]) -> list[GoalSnapshot]:
    if not snapshots:
        return []
    out: list[GoalSnapshot] = []
    seen: set[tuple[str, str]] = set()
    for snap in snapshots:
        key = snap.rendered.strip()
        kind_and_text = (snap.kind, key)
        if not key or kind_and_text in seen:
            continue
        seen.add(kind_and_text)
        out.append(snap)

    has_nontrivial = any(
        s.kind == "goal" and s.rendered.strip().lower() != "no goals"
        for s in out
    )
    if has_nontrivial:
        out = [s for s in out if not (s.kind == "goal" and s.rendered.strip().lower() == "no goals")]
    return out


def _lean_server_cmd(project_root: Path) -> list[str]:
    has_lake = (project_root / "lakefile.lean").exists() or (project_root / "lakefile.toml").exists()
    if has_lake:
        if shutil.which("lake") is None:
            raise LeanToolMissingError("`lake` not found. Install Lean 4 + Lake and try again.")
        return ["lake", "env", "lean", "--server"]
    if shutil.which("lean") is None:
        raise LeanToolMissingError("`lean` not found. Install Lean 4 and try again.")
    return ["lean", "--server"]


def _collect_plain_goals_for_ranges(
    lsp: LspClient,
    uri: str,
    lines: list[str],
    ranges: list[SnippetRange],
    rpc_session_id: object | None,
    snippet_infoview_modes: dict[int, str] | None = None,
    shared_context: bool = False,
) -> dict[int, list[LeanMessage]]:
    if not ranges:
        return {}

    out: dict[int, list[LeanMessage]] = {r.index: [] for r in ranges}
    for snippet_range in ranges:
        mode = "auto"
        if snippet_infoview_modes is not None:
            mode = snippet_infoview_modes.get(snippet_range.index, "auto")
        needs_state_queries = mode != "goals"

        snapshots: list[GoalSnapshot] = []
        if needs_state_queries:
            if shared_context:
                boundary_line = snippet_range.end_line + 1
                if boundary_line < 1:
                    boundary_line = 1
                if boundary_line > len(lines):
                    boundary_line = len(lines)
                line_text = lines[boundary_line - 1]
                local_line = snippet_range.end_line - snippet_range.start_line + 2

                chosen_goal: str | None = None
                fallback_no_goals: str | None = None
                for char in [0]:
                    try:
                        result = lsp.request(
                            "$/lean/plainGoal",
                            {
                                "textDocument": {"uri": uri},
                                "position": {"line": boundary_line - 1, "character": char},
                            },
                        )
                    except Exception:
                        continue
                    if not isinstance(result, dict):
                        continue
                    rendered_raw = str(result.get("rendered", "")).strip()
                    if not rendered_raw:
                        continue
                    rendered = _strip_markdown_fence(rendered_raw)
                    if not rendered:
                        continue
                    if rendered.strip().lower() == "no goals":
                        fallback_no_goals = rendered
                        continue
                    chosen_goal = rendered
                    break

                if chosen_goal is None and fallback_no_goals is not None:
                    chosen_goal = fallback_no_goals

                if chosen_goal is not None:
                    snapshots.append(
                        GoalSnapshot(
                            kind="goal",
                            snippet_line=local_line,
                            rendered=chosen_goal,
                        )
                    )
                elif not line_text.lstrip().startswith("#"):
                    try:
                        term_goal = lsp.request(
                            "$/lean/plainTermGoal",
                            {
                                "textDocument": {"uri": uri},
                                "position": {"line": boundary_line - 1, "character": 0},
                            },
                        )
                    except Exception:
                        term_goal = None
                    if isinstance(term_goal, dict):
                        expected = str(term_goal.get("goal", "")).strip()
                        if expected:
                            snapshots.append(
                                GoalSnapshot(
                                    kind="term",
                                    snippet_line=local_line,
                                    rendered=expected,
                                )
                            )
            else:
                for line_no in range(snippet_range.start_line, snippet_range.end_line + 1):
                    if line_no < 1 or line_no > len(lines):
                        continue
                    line_text = lines[line_no - 1]
                    local_line = line_no - snippet_range.start_line + 1
                    chosen_goal: str | None = None
                    fallback_no_goals: str | None = None
                    for char in _candidate_chars_for_goal(line_text):
                        try:
                            result = lsp.request(
                                "$/lean/plainGoal",
                                {
                                    "textDocument": {"uri": uri},
                                    "position": {"line": line_no - 1, "character": char},
                                },
                            )
                        except Exception:
                            continue
                        if not isinstance(result, dict):
                            continue
                        rendered_raw = str(result.get("rendered", "")).strip()
                        if not rendered_raw:
                            continue
                        rendered = _strip_markdown_fence(rendered_raw)
                        if not rendered:
                            continue
                        if rendered.strip().lower() == "no goals":
                            fallback_no_goals = rendered
                            continue
                        chosen_goal = rendered
                        break

                    if chosen_goal is None and fallback_no_goals is not None:
                        chosen_goal = fallback_no_goals

                    if chosen_goal is not None:
                        snapshots.append(
                            GoalSnapshot(
                                kind="goal",
                                snippet_line=local_line,
                                rendered=chosen_goal,
                            )
                        )
                        continue

                    if line_text.lstrip().startswith("#"):
                        continue

                    for char in _candidate_chars_for_term(line_text):
                        try:
                            term_goal = lsp.request(
                                "$/lean/plainTermGoal",
                                {
                                    "textDocument": {"uri": uri},
                                    "position": {"line": line_no - 1, "character": char},
                                },
                            )
                        except Exception:
                            continue
                        if not isinstance(term_goal, dict):
                            continue
                        expected = str(term_goal.get("goal", "")).strip()
                        if not expected:
                            continue
                        snapshots.append(
                            GoalSnapshot(
                                kind="term",
                                snippet_line=local_line,
                                rendered=expected,
                            )
                        )
                        break

        for snap in _dedupe_goal_snapshots(snapshots):
            label = "tactic state" if snap.kind == "goal" else "expected type"
            out[snippet_range.index].append(
                LeanMessage(
                    severity="info",
                    line=snap.snippet_line,
                    col=1,
                    text=f"[infoview] {label}:\n{snap.rendered}",
                    source="infoview",
                )
            )

        out[snippet_range.index].extend(
            _collect_rpc_message_tab(
                lsp=lsp,
                uri=uri,
                lines=lines,
                snippet_range=snippet_range,
                session_id=rpc_session_id,
                shared_context=shared_context,
            )
        )

    return out


def _collect_with_open_document(
    project_root: Path,
    extracted_lean: Path,
    callback,
):
    text = extracted_lean.read_text(encoding="utf-8")
    lines = text.splitlines()
    uri = extracted_lean.resolve().as_uri()
    cmd = _lean_server_cmd(project_root)

    with LspClient(cmd=cmd, cwd=project_root) as lsp:
        lsp.request(
            "initialize",
            {
                "initializationOptions": {"hasWidgets": True},
                "capabilities": {"lean": {"silentDiagnosticSupport": True}},
            },
        )
        lsp.notify("initialized", {})
        lsp.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "lean",
                    "version": 1,
                    "text": text,
                }
            },
        )
        try:
            lsp.request("textDocument/waitForDiagnostics", {"uri": uri, "version": 1}, timeout_s=180.0)
        except Exception:
            pass

        rpc_session_id: object | None = None
        try:
            connected = lsp.request("$/lean/rpc/connect", {"uri": uri})
            if isinstance(connected, dict):
                rpc_session_id = connected.get("sessionId")
        except Exception:
            rpc_session_id = None

        try:
            return callback(lsp, uri, lines, rpc_session_id)
        finally:
            lsp.notify("textDocument/didClose", {"textDocument": {"uri": uri}})


def collect_plain_goals(
    project_root: Path,
    extracted_lean: Path,
    ranges: list[SnippetRange],
    snippet_infoview_modes: dict[int, str] | None = None,
    shared_context: bool = False,
) -> dict[int, list[LeanMessage]]:
    if not ranges:
        return {}

    return _collect_with_open_document(
        project_root,
        extracted_lean,
        lambda lsp, uri, lines, rpc_session_id: _collect_plain_goals_for_ranges(
            lsp=lsp,
            uri=uri,
            lines=lines,
            ranges=ranges,
            rpc_session_id=rpc_session_id,
            snippet_infoview_modes=snippet_infoview_modes,
            shared_context=shared_context,
        ),
    )


def collect_plain_goals_with_document(
    project_root: Path,
    extracted_lean: Path,
    ranges: list[SnippetRange],
    snippet_infoview_modes: dict[int, str] | None = None,
    shared_context: bool = False,
) -> tuple[dict[int, list[LeanMessage]], list[LeanMessage]]:
    def _collect(lsp: LspClient, uri: str, lines: list[str], rpc_session_id: object | None):
        snippet_messages = _collect_plain_goals_for_ranges(
            lsp=lsp,
            uri=uri,
            lines=lines,
            ranges=ranges,
            rpc_session_id=rpc_session_id,
            snippet_infoview_modes=snippet_infoview_modes,
            shared_context=shared_context,
        )
        if not lines:
            return snippet_messages, []
        document_range = [SnippetRange(index=0, start_line=1, end_line=len(lines))]
        document_messages = _collect_plain_goals_for_ranges(
            lsp=lsp,
            uri=uri,
            lines=lines,
            ranges=document_range,
            rpc_session_id=rpc_session_id,
            snippet_infoview_modes={0: "full"},
            shared_context=False,
        ).get(0, [])
        return snippet_messages, document_messages

    return _collect_with_open_document(project_root, extracted_lean, _collect)
