# LeanTeX v2.5

LeanTeX brings Lean 4 feedback into LaTeX PDFs. Version 2.5 is the recommended version: write Lean code with native `minted`, then ask LeanTeX to render the matching diagnostics or infoview-style output.

```tex
\usepackage[onefile]{leantexv2}

\leantexconfig{natcheck}{infoview=lines:4}
\begin{minted}[label=natcheck]{lean}
#check Nat.succ
example : 1 + 1 = 2 := by decide
\end{minted}

\leantexoutput{natcheck}
```

Hidden output-only snippets are also supported:

```tex
\leantex[infoview=lines:3]{
#check List.map
example : True := by trivial
}
```

## Versions

- `main` — LeanTeX v2.5, current recommended release
- `version2` — earlier minted-based v2 release
- `version1` — original listings-based release

Project page: <https://rgrossharv.github.io/LeanTeX/>

Release: <https://github.com/rgrossharv/LeanTeX/releases/tag/v2.5.0>

## Install

Requirements: Python 3.9+, Lean 4/Lake, a TeX distribution with XeLaTeX or LuaLaTeX, `minted`, and Pygments.

```bash
git clone https://github.com/rgrossharv/LeanTeX.git
cd LeanTeX
python3 -m pip install Pygments
PYTHONPATH=. python3 -m leantex install-tex
```

For Mathlib examples, initialize the example Lake project once:

```bash
cd examples/minimal
lake update
```

## Build

```bash
PYTHONPATH=. python3 -m leantex build path/to/file.tex
```

Lean-only pass:

```bash
PYTHONPATH=. python3 -m leantex build path/to/file.tex --no-latexmk
```

Watch mode:

```bash
PYTHONPATH=. python3 -m leantex watch path/to/file.tex
```

## LaTeX API

- `\leantexconfig{name}{infoview=lines:N}` sets LeanTeX options for a named minted block.
- `\leantexoutput{name}` prints output for a labeled minted block.
- `\leantex[...]{...}` runs hidden Lean code and prints output only.
- `\begin{lean}...\end{lean}` remains available for legacy v2-style blocks.
- `\usepackage[onefile]{leantexv2}` gives snippets a shared Lean context.

Infoview modes: `auto`, `full`, `goals`, `lines:N`.

## Development

```bash
python3 -m unittest discover -s tests -v
```

## License

Public domain dedication via The Unlicense. See [LICENSE](LICENSE).
