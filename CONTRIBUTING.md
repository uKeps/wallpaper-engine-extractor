# Contributing

Thanks for helping out. To run the app from source, see [Run from source](README.md#run-from-source-linux-macos-command-line) in the README.

Python 3.12 in practice, **3.10+ minimum**: the code uses PEP 604 unions (`Path | None`).

## Workflow

`master` is protected: changes land only through a pull request, and three checks must pass.

- `build`: Windows, Python 3.12, unit tests with Pillow, then the exe. A packaging break surfaces here instead of during a release.
- `test-minimal`: Python 3.10 with no optional dependencies, the install path the README promises.
- `lint`: ruff, pyflakes rules only (`F`), pinned version.

Run the same checks locally before pushing:

```bash
python -m unittest discover -s tests
pipx run ruff==0.12.0 check --select F --target-version py310 .
```

Commits and PR titles follow [Conventional Commits](https://www.conventionalcommits.org/). Everything in the repo is in English: code, comments, docs, commit messages.

Releases: bump `assets/version_info.txt` in a PR, then push a `v*` tag. That file is the only place the version lives: `pyproject.toml` reads the PyPI version from its `ProductVersion` line. The tag triggers two workflows: `build.yml` attaches the exe and `checksums.txt` to the release, and `publish.yml` uploads the wheel and sdist to PyPI through trusted publishing (no token in the repo). `build.yml` can also be run by hand from the Actions tab; the exe and checksum then show up as a build artifact instead of a release.

## Optional dependencies are genuinely optional

Pillow and tkinterdnd2 are both listed in `requirements.txt`, but the app must keep working without them. Every use is behind a `HAS_PILLOW` / `HAS_DND` guard with a real fallback: hand-built BMP output in `wallpaper_engine_extractor/tex_parser.py`, plain `tk.Tk` in `wallpaper_engine_extractor/gui.py`. An unguarded import of either one silently breaks the no-dependencies install path that the README promises (`test-minimal` catches it).

## Packaging

`.\build.ps1` produces `dist\WallpaperExtractor.exe` (PyInstaller, onefile, windowed, about 17 MB). Python, Tk, Pillow and the `tkdnd` Tcl package are all bundled in.

Runtime assets live inside the package (`wallpaper_engine_extractor/assets/`), so the wheel ships them, and must be resolved through `resource_path()` in `wallpaper_engine_extractor/gui.py`. A plain relative path works from a source checkout and breaks inside the bundle, where files live under `sys._MEIPASS`; a new asset also needs a `datas` entry in `WallpaperExtractor.spec`. The top-level `assets/` folder holds only what the README and the exe build use.

**If drag-and-drop stops working in a build but works from source, look here first.** tkinterdnd2 ships its support as a Tcl package (`tkdnd`) of `.dll`/`.tcl` files, not as ordinary imports. PyInstaller's contrib hook collects them today. If that ever regresses, `App` in `wallpaper_engine_extractor/gui.py` falls back to plain `tk.Tk` and drag-and-drop just disappears, with no exception and no log line.

The executable is deliberately **unsigned**. A code signing certificate is a recurring yearly cost, and an OV certificate would not even grant immediate SmartScreen reputation. Please open an issue before proposing a signing step; the published SHA256 checksum is the intended substitute. If signing ever happens, [SignPath Foundation](https://signpath.org/) is the route to look at: it gives open source projects that build in public CI a free certificate. See the [README](README.md#is-it-safe-windows-says-it-protected-my-pc) for what users are told.
