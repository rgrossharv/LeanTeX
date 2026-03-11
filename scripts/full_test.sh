#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLE="$ROOT/examples/minimal"
export TEXINPUTS="$ROOT/tex//:${TEXINPUTS:-}"

printf '[full-test] root: %s\n' "$ROOT"

cd "$ROOT"
printf '[full-test] running unit tests...\n'
python3 -m unittest discover -s tests -v

printf '[full-test] checking tools...\n'
command -v python3 >/dev/null
command -v latexmk >/dev/null
if [ -f "$EXAMPLE/lakefile.lean" ] || [ -f "$EXAMPLE/lakefile.toml" ]; then
  command -v lake >/dev/null
else
  command -v lean >/dev/null
fi

printf '[full-test] cleaning previous tex outputs...\n'
rm -f "$EXAMPLE/minimal.pdf" "$EXAMPLE/minimal.aux" "$EXAMPLE/minimal.fls" "$EXAMPLE/minimal.log" "$EXAMPLE/minimal.fdb_latexmk"

printf '[full-test] building with leantex (includes latexmk)...\n'
python3 -m leantex build "$EXAMPLE/minimal.tex"

printf '[full-test] asserting generated include exists...\n'
[ -f "$EXAMPLE/leantex.generated.tex" ]

printf '[full-test] asserting snippet outputs exist...\n'
[ -f "$EXAMPLE/LeanTeX/snippets/snippet_001.out.txt" ]
[ -f "$EXAMPLE/LeanTeX/snippets/snippet_002.out.txt" ]
[ -f "$EXAMPLE/LeanTeX/extracted.infoview.txt" ]

printf '[full-test] asserting expected message routing...\n'
grep -q '\[info\]' "$EXAMPLE/LeanTeX/snippets/snippet_001.out.txt"
grep -q '\[error\]' "$EXAMPLE/LeanTeX/snippets/snippet_002.out.txt"
grep -q '=== Infoview State ===' "$EXAMPLE/LeanTeX/extracted.infoview.txt"

printf '[full-test] asserting pdf exists...\n'
[ -f "$EXAMPLE/minimal.pdf" ]

printf '[full-test] building onefile-mode sample (no latexmk)...\n'
python3 -m leantex build "$EXAMPLE/onefile.tex" --no-latexmk

printf '[full-test] asserting onefile extracted output is shared-context...\n'
if grep -q 'namespace LeanTeX_Snippet_' "$EXAMPLE/LeanTeX/Extracted.lean"; then
  echo "[full-test] expected onefile mode to avoid snippet namespaces" >&2
  exit 1
fi

printf '[full-test] asserting onefile second snippet reuses first declaration...\n'
if grep -q '\[error\]' "$EXAMPLE/LeanTeX/snippets/snippet_002.out.txt"; then
  echo "[full-test] expected no errors in onefile snippet_002" >&2
  exit 1
fi
grep -q 'Goals accomplished' "$EXAMPLE/LeanTeX/snippets/snippet_002.out.txt"

printf '[full-test] PASS\n'
