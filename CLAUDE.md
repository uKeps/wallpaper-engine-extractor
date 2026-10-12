# wallpaper-engine-extractor

Extracts images and videos out of Wallpaper Engine Steam Workshop wallpapers.
Python 3.12 in practice, **3.10+ minimum** — the code uses PEP 604 unions (`Path | None`).

## Workflow

`master` is protected by a ruleset: changes land only through a PR, and three checks
must pass, with no bypass. Branch, open a PR, wait for the checks, then merge.

- `build`: Windows, Python 3.12, unit tests with Pillow, then the exe. A packaging break
  surfaces here instead of during a release.
- `test-minimal`: Python 3.10 with no optional dependencies, the install path the README
  promises.
- `lint`: ruff, pyflakes rules only (`F`), pinned version.

Same checks locally: `python -m unittest discover -s tests` and
`ruff check --select F --target-version py310 .`.

Releases: bump `assets/version_info.txt` in a PR, then push a `v*` tag; the workflow
attaches the exe and `checksums.txt` to the release.

Commits and PRs follow Conventional Commits, in English. Everything that lands in the
repo is English — code, comments, docs, commit messages.

## Optional dependencies are genuinely optional

Pillow and tkinterdnd2 are both listed in `requirements.txt` but the app must keep
working without them. Every use is behind a `HAS_PILLOW` / `HAS_DND` guard with a real
fallback: hand-built BMP output in `src/tex_parser.py`, plain `tk.Tk` in `src/gui.py`.
Adding an unguarded import of either one silently breaks the no-dependencies install
path that the README promises.

## Packaging

`.\build.ps1` produces `dist\WallpaperExtractor.exe` (PyInstaller, onefile, windowed).

Bundled assets must be resolved through `resource_path()` in `src/gui.py` — a plain
relative path works from a source checkout and breaks inside the bundle, where files
live under `sys._MEIPASS`.

**If drag-and-drop ever stops working in a build but works from source, look here
first.** tkinterdnd2 ships its support as a Tcl package (`tkdnd`) of `.dll`/`.tcl`
files, not as ordinary imports. PyInstaller's contrib hook collects them today. If that
ever regresses, `App` in `src/gui.py` falls back to plain `tk.Tk` and drag-and-drop just
disappears — no exception, no log line.

The executable is deliberately **unsigned**. A code signing certificate is a recurring
yearly cost, and an OV certificate would not even grant immediate SmartScreen
reputation. Don't add a signing step without discussing the cost first; the published
SHA256 checksum is the intended substitute. See the README for what users are told.
