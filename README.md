# LeanTeX v2

LeanTeX v2 embeds Lean 4 snippets directly in LaTeX with **minted-based syntax highlighting** and automatic infoview/diagnostics rendering into your PDF.

v2 uses [minted](https://ctan.org/pkg/minted) + [Pygments](https://pygments.org/) for true syntax highlighting (colored keywords, tactics, types, strings, comments) and requires **XeLaTeX** or **LuaLaTeX** for native Unicode support.

## Features

- `\begin{lean} ... \end{lean}` blocks in LaTeX with full Pygments syntax highlighting
- Per-snippet infoview output with colored boxes (charcoal for code/info, red for errors)
- `show=both`, `show=code`, or `show=output` display control per block
- One-file shared context mode: `\usepackage[onefile]{leantexv2}`
- Comprehensive Unicode fallback (130+ Lean symbols via STIX Two Math / Apple Symbols / Symbola)
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
| `fontspec` | any | Included with XeLaTeX/LuaLaTeX distributions |

### Recommended Fonts (optional)

For best Unicode symbol coverage, install one of these monospace fonts (checked in this order):

1. **JuliaMono** — best Lean coverage ([juliamono.netlify.app](https://juliamono.netlify.app/))
2. **DejaVu Sans Mono** — good coverage, widely available
3. **Noto Sans Mono** — good coverage
4. **Menlo** — macOS default; missing symbols auto-fallback to STIX Two Math

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

This copies `leantexv2.sty` into your local TeX tree and installs the latexmk hook into `~/.latexmkrc`:

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

LeanTeX v2 is designed to work with the [LaTeX Workshop](https://marketplace.visualstudio.com/items?itemName=james-yu.latex-workshop) extension in VS Code. Once set up, pressing the **green ▶ play button** (or `Ctrl+Alt+B` / `Cmd+Alt+B`) will run the full LeanTeX + LaTeX pipeline automatically.

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
        "name": "LeanTeX v2 (xelatex)",
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

\begin{lean}[show=both]
#check Nat.succ
example : 1 + 1 = 2 := by decide
\end{lean}
```

### Display options

| Option | Effect |
|---|---|
| `show=both` | Show code block and infoview output (default) |
| `show=code` | Show code block only |
| `show=output` | Show infoview output only |

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

## What's New in v2 (vs v1)

| Feature | v1 | v2 |
|---|---|---|
| Syntax highlighting | `listings` (monochrome) | `minted` / Pygments (full color) |
| Unicode handling | U+XXXX encoding + literate maps | Native UTF-8 + automatic font fallback |
| TeX engine | pdflatex, xelatex, lualatex | **XeLaTeX or LuaLaTeX only** |
| Unicode symbols | ~80 static mappings | 130+ with automatic fallback to STIX Two Math |
| Title bars | Plain gray | Charcoal (code / info) · Red (errors) · White text |

---

## License

Public domain dedication via The Unlicense (see `LICENSE`).

## Citation

If you used LeanTeX in your work and want to give credit (you definitely don't have to!):

**MLA:** Gross, Ryland. *LeanTeX v2*. 2026. GitHub, https://github.com/rgrossharv/LeanTeX.

**BibTeX:**
```bibtex
@software{gross2026leantexv2,
  author  = {Gross, Ryland},
  title   = {{LeanTeX v2}},
  year    = {2026},
  url     = {https://github.com/rgrossharv/LeanTeX},
}
```
