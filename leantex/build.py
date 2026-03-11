from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from .extractor import write_extracted_lean
from .infoview import LeanLspError, collect_plain_goals_with_document
from .models import BuildContext, BuildResult, LeanMessage, Snippet, SnippetRange
from .parser import detect_shared_context_mode, parse_tex_for_lean
from .render import write_generated_assets
from .runner import LeanToolMissingError, run_lean

IMPORT_STMT_RE = re.compile(r"^\s*import\s+(?P<mods>.+?)\s*$")
UNKNOWN_MODULE_RE = re.compile(r"unknown module prefix ['`](?P<mod>[A-Za-z0-9_.]+)['`]", re.IGNORECASE)
NO_DIR_MODULE_RE = re.compile(r"No directory ['`](?P<mod>[A-Za-z0-9_.]+)['`] or file", re.IGNORECASE)
MODULE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.]+$")
CACHE_SCHEMA = 1
WORKSPACE_MANIFEST = ".leantex-workspace.json"
WORKSPACE_FIXED_NAMES = {
    ".lake",
    "lakefile.lean",
    "lakefile.toml",
    "lake-manifest.json",
    "lean-toolchain",
}
WORKSPACE_SKIP_NAMES = {
    ".git",
    ".github",
    ".lake",
    "LeanTeX",
    "build",
    "%OUTDIR%",
}


def _has_lakefile(path: Path) -> bool:
    return (path / "lakefile.lean").exists() or (path / "lakefile.toml").exists()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def _symlink_or_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = str(src.resolve())
    if dest.is_symlink():
        try:
            if os.readlink(dest) == target:
                return
        except OSError:
            pass
    if dest.exists() or dest.is_symlink():
        _remove_path(dest)
    try:
        dest.symlink_to(target, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)


def _workspace_manifest_path(generated_dir: Path) -> Path:
    return generated_dir / WORKSPACE_MANIFEST


def _load_workspace_manifest(generated_dir: Path) -> dict[str, object]:
    path = _workspace_manifest_path(generated_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _collect_imported_modules(snippets: list[Snippet]) -> set[str]:
    modules: set[str] = set()
    for snip in snippets:
        for line in snip.code.splitlines():
            modules.update(_parse_import_modules(line))
    return modules


def _required_source_entries(project_root: Path, snippets: list[Snippet]) -> list[str]:
    entries: set[str] = set()
    for mod in _collect_imported_modules(snippets):
        top = mod.split(".", 1)[0]
        file_candidate = project_root / f"{top}.lean"
        dir_candidate = project_root / top
        if file_candidate.exists():
            entries.add(f"{top}.lean")
        if dir_candidate.exists() and dir_candidate.is_dir():
            entries.add(top)
    return sorted(entries)


def _sync_generated_workspace(
    generated_dir: Path,
    project_root: Path,
    snippets: list[Snippet],
) -> None:
    if _is_within(generated_dir, project_root):
        return
    if not _has_lakefile(project_root):
        return

    generated_dir.mkdir(parents=True, exist_ok=True)

    tracked: set[str] = set()
    for name in ("lakefile.lean", "lakefile.toml", "lake-manifest.json", "lean-toolchain"):
        src = project_root / name
        if not src.exists():
            continue
        _symlink_or_copy(src, generated_dir / name)
        tracked.add(name)

    lake_dir = project_root / ".lake"
    if lake_dir.exists():
        _symlink_or_copy(lake_dir, generated_dir / ".lake")
        tracked.add(".lake")

    for name in _required_source_entries(project_root, snippets):
        _symlink_or_copy(project_root / name, generated_dir / name)
        tracked.add(name)

    previous = _load_workspace_manifest(generated_dir)
    prev_entries = previous.get("entries")
    if isinstance(prev_entries, list):
        for raw in prev_entries:
            if not isinstance(raw, str):
                continue
            if raw in tracked:
                continue
            if raw in {"snippets", "cache.json", "Extracted.lean"}:
                continue
            _remove_path(generated_dir / raw)

    manifest = {
        "project_root": str(project_root.resolve()),
        "entries": sorted(tracked),
    }
    _workspace_manifest_path(generated_dir).write_text(
        json.dumps(manifest, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    while True:
        if _has_lakefile(current):
            return current
        if current.parent == current:
            return start.resolve()
        current = current.parent


def _resolve_project_root_override(project_root_override: Path | None) -> Path | None:
    env_override = os.environ.get("LEANTEX_PROJECT_ROOT")
    chosen = project_root_override
    if chosen is None and env_override:
        chosen = Path(env_override)
    if chosen is None:
        return None
    resolved = chosen.expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f"project root does not exist or is not a directory: {resolved}")
    return resolved


def create_context(tex_path: Path, project_root_override: Path | None = None) -> BuildContext:
    tex_path = tex_path.resolve()
    tex_dir = tex_path.parent
    override_root = _resolve_project_root_override(project_root_override)
    project_root = override_root if override_root is not None else find_project_root(tex_dir)
    generated_dir = tex_dir / "LeanTeX"
    snippets_dir = generated_dir / "snippets"
    output_dir = generated_dir

    return BuildContext(
        tex_path=tex_path,
        tex_dir=tex_dir,
        project_root=project_root,
        generated_dir=generated_dir,
        extracted_lean_path=generated_dir / "Extracted.lean",
        generated_tex_path=tex_dir / "leantex.generated.tex",
        snippets_dir=snippets_dir,
        output_dir=output_dir,
    )


def _attribute_messages(
    ranges: list[SnippetRange],
    messages: list[LeanMessage],
) -> tuple[dict[int, list[LeanMessage]], list[LeanMessage]]:
    by_snippet: dict[int, list[LeanMessage]] = {r.index: [] for r in ranges}
    global_messages: list[LeanMessage] = []

    for msg in messages:
        if msg.line is None:
            global_messages.append(msg)
            continue
        matched = False
        for r in ranges:
            if r.start_line <= msg.line <= r.end_line:
                local_line = msg.line - r.start_line + 1
                local_end_line = None
                if msg.end_line is not None:
                    local_end_line = msg.end_line - r.start_line + 1
                by_snippet[r.index].append(
                    replace(
                        msg,
                        line=local_line,
                        end_line=local_end_line,
                    )
                )
                matched = True
                break
        if not matched:
            global_messages.append(msg)

    return by_snippet, global_messages


def _message_to_obj(msg: LeanMessage) -> dict[str, object]:
    return {
        "severity": msg.severity,
        "text": msg.text,
        "line": msg.line,
        "col": msg.col,
        "end_line": msg.end_line,
        "end_col": msg.end_col,
        "source": msg.source,
    }


def _message_from_obj(obj: dict[str, object]) -> LeanMessage:
    return LeanMessage(
        severity=str(obj.get("severity", "info")),
        text=str(obj.get("text", "")),
        line=obj.get("line") if isinstance(obj.get("line"), int) else None,
        col=obj.get("col") if isinstance(obj.get("col"), int) else None,
        end_line=obj.get("end_line") if isinstance(obj.get("end_line"), int) else None,
        end_col=obj.get("end_col") if isinstance(obj.get("end_col"), int) else None,
        source=str(obj.get("source", "lean")),
    )


def _hash_file_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()


def _build_signature(
    context: BuildContext,
    extracted_text: str,
    snippets: list[Snippet],
    shared_context: bool,
) -> dict[str, object]:
    lean_toolchain_hash = _hash_file_if_exists(context.project_root / "lean-toolchain")

    lakefile_hash = ""
    for candidate in (context.project_root / "lakefile.lean", context.project_root / "lakefile.toml"):
        if candidate.exists():
            lakefile_hash = _hash_file_if_exists(candidate)
            break

    return {
        "schema": CACHE_SCHEMA,
        "project_root": str(context.project_root.resolve()),
        "extracted_sha256": hashlib.sha256(extracted_text.encode("utf-8")).hexdigest(),
        "lean_toolchain_sha256": lean_toolchain_hash,
        "lakefile_sha256": lakefile_hash,
        "snippet_infoview_modes": [s.infoview for s in snippets],
        "shared_context": shared_context,
    }


def _cache_disabled() -> bool:
    raw = os.environ.get("LEANTEX_NO_CACHE", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _cache_path(context: BuildContext) -> Path:
    return context.generated_dir / "cache.json"


def _load_cache(
    context: BuildContext,
    signature: dict[str, object],
) -> tuple[dict[int, list[LeanMessage]], list[LeanMessage], list[LeanMessage], str] | None:
    if _cache_disabled():
        return None

    path = _cache_path(context)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("signature") != signature:
        return None

    raw_by = payload.get("by_snippet")
    raw_document = payload.get("document_messages")
    raw_global = payload.get("global_messages")
    raw_output = payload.get("raw_output")
    if (
        not isinstance(raw_by, dict)
        or not isinstance(raw_document, list)
        or not isinstance(raw_global, list)
        or not isinstance(raw_output, str)
    ):
        return None

    by_snippet: dict[int, list[LeanMessage]] = {}
    for k, items in raw_by.items():
        if not isinstance(k, str) or not isinstance(items, list):
            continue
        try:
            idx = int(k)
        except ValueError:
            continue
        parsed: list[LeanMessage] = []
        for item in items:
            if isinstance(item, dict):
                parsed.append(_message_from_obj(item))
        by_snippet[idx] = parsed

    document_messages: list[LeanMessage] = []
    for item in raw_document:
        if isinstance(item, dict):
            document_messages.append(_message_from_obj(item))

    global_messages: list[LeanMessage] = []
    for item in raw_global:
        if isinstance(item, dict):
            global_messages.append(_message_from_obj(item))

    return by_snippet, document_messages, global_messages, raw_output


def _save_cache(
    context: BuildContext,
    signature: dict[str, object],
    by_snippet: dict[int, list[LeanMessage]],
    document_messages: list[LeanMessage],
    global_messages: list[LeanMessage],
    raw_output: str,
) -> None:
    if _cache_disabled():
        return

    payload = {
        "signature": signature,
        "by_snippet": {
            str(idx): [_message_to_obj(m) for m in msgs]
            for idx, msgs in by_snippet.items()
        },
        "document_messages": [_message_to_obj(m) for m in document_messages],
        "global_messages": [_message_to_obj(m) for m in global_messages],
        "raw_output": raw_output,
    }
    path = _cache_path(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def _parse_import_modules(line: str) -> list[str]:
    m = IMPORT_STMT_RE.match(line)
    if not m:
        return []
    mods_part = m.group("mods").split("--", 1)[0].strip()
    if not mods_part:
        return []
    modules: list[str] = []
    for token in mods_part.split():
        tok = token.strip()
        if not tok or not MODULE_TOKEN_RE.match(tok):
            continue
        modules.append(tok)
    return modules


def _collect_import_locations(
    snippets: list[Snippet],
) -> tuple[dict[str, list[tuple[int, int]]], dict[str, list[tuple[int, int]]]]:
    module_locations: dict[str, list[tuple[int, int]]] = {}
    stmt_locations: dict[str, list[tuple[int, int]]] = {}
    for snip in snippets:
        for line_no, line in enumerate(snip.code.splitlines(), start=1):
            modules = _parse_import_modules(line)
            if not modules:
                continue
            stmt = line.strip()
            stmt_locations.setdefault(stmt, []).append((snip.index, line_no))
            for mod in modules:
                module_locations.setdefault(mod, []).append((snip.index, line_no))
    return module_locations, stmt_locations


def _extract_module_prefix(text: str) -> str | None:
    for pattern in (UNKNOWN_MODULE_RE, NO_DIR_MODULE_RE):
        m = pattern.search(text)
        if m:
            return m.group("mod")
    return None


def _route_global_import_messages(
    snippets: list[Snippet],
    hoisted_import_line_to_stmt: dict[int, str],
    by_snippet: dict[int, list[LeanMessage]],
    global_messages: list[LeanMessage],
) -> list[LeanMessage]:
    module_locations, stmt_locations = _collect_import_locations(snippets)
    remaining: list[LeanMessage] = []

    for msg in global_messages:
        targets: list[tuple[int, int]] = []

        if msg.line is not None and msg.line in hoisted_import_line_to_stmt:
            stmt = hoisted_import_line_to_stmt[msg.line]
            targets.extend(stmt_locations.get(stmt, []))
            for mod in _parse_import_modules(stmt):
                targets.extend(module_locations.get(mod, []))

        prefix = _extract_module_prefix(msg.text)
        if prefix:
            for mod, locs in module_locations.items():
                if mod == prefix or mod.startswith(prefix + "."):
                    targets.extend(locs)

        unique_targets: list[tuple[int, int]] = []
        seen_targets: set[tuple[int, int]] = set()
        for target in targets:
            if target in seen_targets:
                continue
            seen_targets.add(target)
            unique_targets.append(target)

        if not unique_targets:
            remaining.append(msg)
            continue

        col = msg.col if msg.col is not None and msg.col > 0 else 1
        for snippet_idx, import_line in unique_targets:
            by_snippet.setdefault(snippet_idx, []).append(
                replace(msg, line=import_line, col=col)
            )

    return remaining


def _snippets_have_imports(snippets: list[Snippet]) -> bool:
    for snip in snippets:
        for line in snip.code.splitlines():
            if _parse_import_modules(line):
                return True
    return False


def _has_unresolved_import_errors(messages: list[LeanMessage]) -> bool:
    for msg in messages:
        text = msg.text
        if UNKNOWN_MODULE_RE.search(text) or NO_DIR_MODULE_RE.search(text):
            return True
    return False


def _discover_lake_project_candidates(tex_dir: Path) -> list[Path]:
    bases: list[Path] = [tex_dir]
    if tex_dir.parent != tex_dir:
        bases.append(tex_dir.parent)
    if tex_dir.parent.parent != tex_dir.parent:
        bases.append(tex_dir.parent.parent)

    found: dict[str, Path] = {}
    for base in bases:
        base = base.resolve()
        if _has_lakefile(base):
            found[str(base)] = base
        try:
            for child in sorted(base.iterdir()):
                if child.is_dir() and _has_lakefile(child):
                    found[str(child.resolve())] = child.resolve()
        except OSError:
            continue

    return [found[k] for k in sorted(found.keys())]


def _select_retry_project_root(
    context: BuildContext,
    snippets: list[Snippet],
    messages: list[LeanMessage],
) -> tuple[Path, list[LeanMessage], str, LeanMessage | None]:
    if _has_lakefile(context.project_root):
        return context.project_root, messages, "", None
    if not _snippets_have_imports(snippets):
        return context.project_root, messages, "", None
    if not _has_unresolved_import_errors(messages):
        return context.project_root, messages, "", None

    candidates = [
        c for c in _discover_lake_project_candidates(context.tex_dir)
        if c.resolve() != context.project_root.resolve()
    ]
    for candidate in candidates:
        try:
            retry_messages, retry_raw = run_lean(candidate, context.extracted_lean_path)
        except (LeanToolMissingError, OSError):
            continue
        if _has_unresolved_import_errors(retry_messages):
            continue
        return (
            candidate,
            retry_messages,
            retry_raw,
            LeanMessage(
                severity="info",
                text=f"using nearby Lake project root: {candidate}",
                source="build",
            ),
        )

    return context.project_root, messages, "", None


def process(tex_path: Path, project_root_override: Path | None = None) -> BuildResult:
    context = create_context(tex_path, project_root_override=project_root_override)
    snippets = parse_tex_for_lean(context.tex_path)
    shared_context = detect_shared_context_mode(context.tex_path)

    extracted = write_extracted_lean(
        context.extracted_lean_path,
        snippets,
        shared_context=shared_context,
    )
    ranges = extracted.ranges
    extracted_text = context.extracted_lean_path.read_text(encoding="utf-8")
    signature = _build_signature(context, extracted_text, snippets, shared_context)

    cached = _load_cache(context, signature)
    if cached is not None:
        by_snippet, document_messages, global_messages, raw_output = cached
        for snip in snippets:
            by_snippet.setdefault(snip.index, [])
    else:
        messages, raw_output = run_lean(context.project_root, context.extracted_lean_path)
        document_messages = list(messages)

        retry_root, retry_messages, retry_raw_output, retry_note = _select_retry_project_root(
            context=context,
            snippets=snippets,
            messages=messages,
        )
        if retry_root != context.project_root:
            context.project_root = retry_root
            messages = retry_messages
            raw_output = retry_raw_output
            document_messages = list(messages)
            signature = _build_signature(context, extracted_text, snippets, shared_context)
            cached_retry = _load_cache(context, signature)
            if cached_retry is not None:
                by_snippet, document_messages, global_messages, raw_output = cached_retry
                for snip in snippets:
                    by_snippet.setdefault(snip.index, [])
                _sync_generated_workspace(
                    context.generated_dir,
                    context.project_root,
                    snippets,
                )
                write_generated_assets(
                    generated_tex_path=context.generated_tex_path,
                    snippets_dir=context.snippets_dir,
                    snippets=snippets,
                    snippet_messages=by_snippet,
                    document_messages=document_messages,
                )
                return BuildResult(
                    snippets=snippets,
                    snippet_messages=by_snippet,
                    document_messages=document_messages,
                    global_messages=global_messages,
                    raw_output=raw_output,
                )

        _sync_generated_workspace(
            context.generated_dir,
            context.project_root,
            snippets,
        )
        by_snippet, global_messages = _attribute_messages(ranges, messages)
        global_messages = _route_global_import_messages(
            snippets=snippets,
            hoisted_import_line_to_stmt=extracted.hoisted_import_line_to_stmt,
            by_snippet=by_snippet,
            global_messages=global_messages,
        )
        if retry_note is not None:
            global_messages.append(retry_note)

        snippet_modes = {snip.index: snip.infoview for snip in snippets}
        try:
            infoview_messages, document_infoview_messages = collect_plain_goals_with_document(
                project_root=context.project_root,
                extracted_lean=context.extracted_lean_path,
                ranges=ranges,
                snippet_infoview_modes=snippet_modes,
                shared_context=shared_context,
            )
            for snippet_idx, extra in infoview_messages.items():
                by_snippet.setdefault(snippet_idx, []).extend(extra)
            document_messages.extend(document_infoview_messages)
        except (LeanToolMissingError, LeanLspError, TimeoutError, OSError) as exc:
            warning = LeanMessage(
                severity="warning",
                text=f"infoview goal extraction skipped: {exc}",
                source="infoview",
            )
            global_messages.append(warning)
            document_messages.append(warning)

        _save_cache(
            context=context,
            signature=signature,
            by_snippet=by_snippet,
            document_messages=document_messages,
            global_messages=global_messages,
            raw_output=raw_output,
        )
    if cached is not None:
        _sync_generated_workspace(
            context.generated_dir,
            context.project_root,
            snippets,
        )

    write_generated_assets(
        generated_tex_path=context.generated_tex_path,
        snippets_dir=context.snippets_dir,
        snippets=snippets,
        snippet_messages=by_snippet,
        document_messages=document_messages,
    )

    return BuildResult(
        snippets=snippets,
        snippet_messages=by_snippet,
        document_messages=document_messages,
        global_messages=global_messages,
        raw_output=raw_output,
    )


def run_latexmk(tex_path: Path) -> None:
    def _normalized_engines() -> list[str]:
        raw = os.environ.get("LEANTEX_LATEX_ENGINE", "auto").strip().lower()
        if raw in {"", "auto"}:
            return ["xelatex", "lualatex", "pdflatex"]
        if raw in {"lualatex", "lua"}:
            return ["lualatex"]
        if raw in {"xelatex", "xe"}:
            return ["xelatex"]
        if raw in {"pdflatex", "pdf"}:
            return ["pdflatex"]
        return ["pdflatex"]

    def _engine_flag(engine: str) -> str:
        if engine == "lualatex":
            return "-lualatex"
        if engine == "xelatex":
            return "-xelatex"
        return "-pdf"

    def _run(engine: str, force: bool = False) -> subprocess.CompletedProcess[str]:
        cmd = ["latexmk", _engine_flag(engine), "-interaction=nonstopmode"]
        if force:
            cmd.append("-g")
        cmd.append(tex_path.name)

        return subprocess.run(
            cmd,
            cwd=tex_path.parent,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    env["LC_CTYPE"] = "C"
    failures: list[tuple[str, subprocess.CompletedProcess[str]]] = []
    for engine in _normalized_engines():
        proc = _run(engine=engine, force=False)
        if proc.returncode != 0:
            stale_prev_error = (
                "Nothing to do for" in proc.stdout
                and "previous invocation" in proc.stdout
            )
            if stale_prev_error:
                proc = _run(engine=engine, force=True)
        if proc.returncode == 0:
            return
        failures.append((engine, proc))

    details: list[str] = []
    for engine, proc in failures:
        details.append(
            f"engine={engine}\nstdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}\n"
        )
    raise RuntimeError("latexmk failed for all engines.\n" + "\n---\n".join(details))
