# LeanTeX

LeanTeX lets you embed Lean 4 snippets directly in LaTeX and render both code and Lean diagnostics/output into your PDF.

## Features

- `\begin{lean} ... \end{lean}` blocks in LaTeX
- Per-snippet output rendering and infoview summaries
- One-file shared context mode (`[onefile]`)
- Caching for faster rebuilds
- CLI modes: `build`, `watch`, and `install-tex`

## Repository Layout

- `leantex/` Python package and CLI
- `tex/` LaTeX style files (`leantex.sty`, `leantexonefile.sty`)
- `examples/minimal/` runnable demo project
- `tests/` unit tests
- `scripts/full_test.sh` end-to-end local check

## Requirements

- Python 3.9+
- Lean 4 and Lake
- TeX distribution with `latexmk`, `listings`, `tcolorbox`, `comment`

## Install 

### 1) Clone

```bash
git clone https://github.com/<your-org-or-user>/LeanTeX.git
cd LeanTeX
```

### 2) Install Python package

```bash
python3 -m pip install .
```

For local development, editable install:

```bash
python3 -m pip install -e .
```

If your `pip` is older and reports `invalid command 'bdist_wheel'`, install build helpers first:

```bash
python3 -m pip install --upgrade pip setuptools wheel
```

### 3) Install LaTeX package files

```bash
leantex install-tex
```

This installs:

- `leantex.sty`
- `leantexonefile.sty`

and updates `~/.latexmkrc` with a LeanTeX hook for `latexmk`.

## Quick Start

In your document:

```tex
\usepackage{leantex}
```

Build once:

```bash
leantex build path/to/file.tex
```

Watch mode:

```bash
leantex watch path/to/file.tex
```

Without installing the CLI globally:

```bash
PYTHONPATH=. python3 -m leantex build path/to/file.tex
```

## Example

Use the demo in `examples/minimal/`:

```bash
cd examples/minimal
PYTHONPATH=../.. python3 -m leantex build minimal.tex
```

## LaTeX Usage

Basic:

```tex
\begin{lean}[name=demo,show=both]
#check Nat.succ
\end{lean}
```

Shared context mode:

```tex
\usepackage[onefile]{leantex}
```

or

```tex
\usepackage{leantexonefile}
```

## Useful Environment Variables

- `LEANTEX_PROJECT_ROOT` override Lake project root
- `LEANTEX_NO_CACHE=1` disable cache
- `LEANTEX_LATEX_ENGINE` set engine (`auto`, `pdflatex`, `xelatex`, `lualatex`)

## Development

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

Run full local check:

```bash
./scripts/full_test.sh
```

## GitHub Release Checklist

Before pushing this repo to GitHub:

1. Run `python3 -m unittest discover -s tests -v`
2. Run `./scripts/full_test.sh` (if Lean + latexmk are installed)
3. Confirm no generated artifacts are committed (see `.gitignore`)
4. Push to GitHub

Example:

```bash
git init
git add .
git commit -m "Initial LeanTeX release"
git branch -M main
git remote add origin https://github.com/<your-org-or-user>/LeanTeX.git
git push -u origin main
```
