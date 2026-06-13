# LeanTeX v2.5

LeanTeX v2.5 lets you write normal, native `minted` Lean code while LeanTeX renders the matching Lean diagnostics and infoview-style output in your PDF. It is designed for mathematical writing where the Lean source should look like ordinary LaTeX code listings, but the proof state, errors, or completion messages should still be available in the final document.

v2.5 keeps the older v2 `lean` environment available, but the recommended workflow is lighter: write code in `minted`, then call `\leantexoutput{name}` for the infoview, or use `\leantex{...}` when you want a hidden Lean snippet that prints only output.

## Branches

- `main` — LeanTeX v2.5, the current recommended version
- `version2` — the earlier minted-based v2 line
- `version1` — the original listings-based implementation

## Features

- Native `\begin{minted}{lean} ... \end{minted}` code blocks
- `\leantex{...}` hidden Lean snippets that render infoview output only
- `\leantexoutput{name}` to print infoview for a named minted block
- Native minted output that is rendered plainly, without an extra LeanTeX box or heading
- Legacy `\begin{lean}` blocks remain available with the original v2 boxed display
- `infoview=auto`, `infoview=full`, `infoview=goals`, and `infoview=lines:N`
- One-file shared context mode: `\usepackage[onefile]{leantexv2}`
- Output-only v2.5 blocks avoid writing duplicate generated code files
- Caching for faster rebuilds
- CLI modes: `build`, `watch`, and `install-tex`

## Repository Layout

- `leantex/` — Python package and CLI
- `tex/` — LaTeX style files (`leantexv2.sty`, `leantexv2onefile.sty`)
- `examples/minimal/` — runnable demo project (includes `project.pdf`)
- `tests/` — unit tests
- `scripts/full_test.sh` — end-to-end local check

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.9+ | |
| Lean 4 + Lake | latest | Install via [elan](https://github.com/leanprover/elan) |
| TeX distribution | any | Must include XeLaTeX or LuaLaTeX |
| `latexmk` | any | Included in most TeX distributions |
| `minted` | 2.0+ | LaTeX package (CTAN) |
| `Pygments` | any | `pip install Pygments` — provides the `pygmentize` command |
| `tcolorbox` | any | LaTeX package (CTAN) |

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/rgrossharv/LeanTeX.git
cd LeanTeX
```

### 2. Install Pygments

Pygments provides the `pygmentize` command that minted uses for syntax highlighting:

```bash
python3 -m pip install Pygments
```

### 3. Install the LaTeX style files

This copies the LeanTeX style files into your local TeX tree and installs the latexmk hook into `~/.latexmkrc`:

```bash
PYTHONPATH=. python3 -m leantex install-tex
```

You only need to do this once. If you ever move or rename the repo folder, re-run this command.

### 4. (For Mathlib projects) Download the Lean cache

If your document imports Mathlib, you need to download the compiled Mathlib cache once. From the example project folder:

```bash
cd examples/minimal
lake update
```

This downloads ~6–8 GB and can take a few minutes. It only needs to be done once per Lean toolchain version.

---

## VS Code: One-Click Build

LeanTeX is designed to work with the [LaTeX Workshop](https://marketplace.visualstudio.com/items?itemName=james-yu.latex-workshop) extension in VS Code. Once set up, pressing the green play button (or `Ctrl+Alt+B` / `Cmd+Alt+B`) will run the full LeanTeX + LaTeX pipeline automatically.

### Setup

Add the following to your VS Code **user** `settings.json` (`Cmd+Shift+P` → *Preferences: Open User Settings (JSON)*):

```json
"latex-workshop.latex.tools": [
    {
        "name": "latexmk-xelatex",
        "command": "latexmk",
        "args": [
            "-xelatex",
            "-shell-escape",
            "-interaction=nonstopmode",
            "-synctex=1",
            "%DOC%"
        ],
        "env": {
            "PATH": "/Users/YOUR_USERNAME/.elan/bin:/Users/YOUR_USERNAME/Library/Python/3.9/bin:/Library/TeX/texbin:/usr/local/bin:/usr/bin:/bin"
        }
    }
],
"latex-workshop.latex.recipes": [
    {
        "name": "LeanTeX v2.5 (xelatex)",
        "tools": ["latexmk-xelatex"]
    }
],
"latex-workshop.latex.recipe.default": "first"
```

> **Replace `YOUR_USERNAME`** with your macOS username (the folder name under `/Users/`).

The three `PATH` entries that matter:
- `/Users/YOUR_USERNAME/.elan/bin` — makes `lake` available (needed for Lean/Mathlib)
- `/Users/YOUR_USERNAME/Library/Python/3.9/bin` — makes `pygmentize` available (needed for minted)
- `/Library/TeX/texbin` — makes `latexmk` and `xelatex` available

### How it works

When you click the play button, VS Code calls `latexmk -xelatex -shell-escape`. The `~/.latexmkrc` hook installed by `leantex install-tex` intercepts the `xelatex` call and:

1. Runs `python3 -m leantex build yourfile.tex` — compiles your Lean snippets and writes the infoview output
2. Runs `xelatex --shell-escape yourfile.tex` — builds the final PDF with minted syntax highlighting

The first build is slower (Lean compilation). Subsequent builds use the cache and are much faster.

---

## Command Line Usage

Build once:

```bash
PYTHONPATH=. python3 -m leantex build path/to/file.tex
```

Skip the PDF step (Lean only):

```bash
PYTHONPATH=. python3 -m leantex build path/to/file.tex --no-latexmk
```

Watch mode (rebuild on file change):

```bash
PYTHONPATH=. python3 -m leantex watch path/to/file.tex
```

Run xelatex manually:

```bash
xelatex --shell-escape yourfile.tex
```

---

## LaTeX Usage

### Basic

```tex
\usepackage[onefile]{leantexv2}

\leantexconfig{natcheck}{infoview=goals}
\begin{minted}[label=natcheck]{lean}
#check Nat
example : 1 + 1 = 2 := by decide
\end{minted}

\leantexoutput{natcheck}

\leantex[infoview=lines:3]{
#check List.map
example : True := by
  trivial
}
```

### Infoview options

| Option | Effect |
|---|---|
| `infoview=auto` | Compact default output |
| `infoview=full` | Full diagnostics and infoview state |
| `infoview=goals` | Goal/message focused output |
| `infoview=lines:N` | First `N` lines of infoview state |

For named minted blocks, put LeanTeX-only options in `\leantexconfig{name}{...}` so minted receives only minted options.

The original v2-style block still works when you want LeanTeX to render code too:

```tex
\begin{lean}[show=both,infoview=auto]
#check Nat.succ
\end{lean}
```

### Shared context mode

Definitions from earlier blocks are visible in later ones:

```tex
\usepackage[onefile]{leantexv2}
% or: \usepackage{leantexv2onefile}
```

### Full extracted infoview

Dump the complete infoview output for the whole document at any point:

```tex
\totalinfoview
```

### Customization

```tex
% Font size for code and output boxes
\leantexsetdefaultcodesize{\footnotesize}
\leantexsetdefaultoutputsize{\scriptsize}

% Change the Pygments color theme (default: tango)
\leantexsetmintedstyle{monokai}

% Pass extra options to minted
\leantexsetcodestyle{linenos=true}
```

---

## Useful Environment Variables

- `LEANTEX_PROJECT_ROOT` — override Lake project root detection
- `LEANTEX_NO_CACHE=1` — disable the build cache
- `LEANTEX_LATEX_ENGINE` — set engine (`auto`, `xelatex`, `lualatex`)

---

## Development

Run unit tests:

```bash
python3 -m unittest discover -s tests -v
```

Run the full end-to-end test (requires Lean + latexmk):

```bash
./scripts/full_test.sh
```

---

## What's New in v2.5

| Feature | Earlier versions | v2.5 |
|---|---|---|
| Recommended Lean source | LeanTeX `lean` environment | Native `minted` blocks |
| Infoview for displayed source | Coupled to the LeanTeX environment | `\leantexoutput{name}` after a labeled minted block |
| Hidden Lean snippets | Less direct | `\leantex[infoview=...]{...}` |
| Generated files | Code and output for most snippets | Output-only snippets avoid duplicate code files |
| Legacy v2 blocks | Primary workflow | Still supported |

## v2 vs v1

| Feature | v1 | v2 / v2.5 |
|---|---|---|
| Syntax highlighting | `listings` | `minted` / Pygments |
| Unicode handling | U+XXXX encoding + literate maps | Native UTF-8 + font fallback |
| TeX engine | pdflatex, xelatex, lualatex | **XeLaTeX or LuaLaTeX only** |
| Unicode symbols | Static mappings | Automatic fallback to STIX Two Math |

---

## License

Public domain dedication via The Unlicense (see `LICENSE`).

## AI Acknowledgement

LeanTeX was built with substantial AI-assisted development and human review.
