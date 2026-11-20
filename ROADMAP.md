# Wallpaper Engine Extractor — Roadmap

## Now
<!-- In progress. At most 3. Each names its branch/PR when it has one. -->
- [ ] N1 — v1.2.0 release — next step: configure PyPI trusted publisher (`pypi` environment in GitHub repo settings + pending publisher on pypi.org for `publish.yml`), then bump all 4 version fields in `assets/version_info.txt` to `1.2.0` in a PR and push the `v1.2.0` tag

## Next
<!-- Ordered; the top item is what starts when Now frees up. At most 10. -->
1. README PyPI install section: document `pipx install wallpaper-engine-extractor[full]` (and base install without `[full]`) once `v1.2.0` is live on PyPI — why: `#9` packaged for PyPI and `D1` refers to `pipx`, while the README still only shows `git clone`
2. winget: write portable manifests for 1.2.0 (`uKeps.WallpaperEngineExtractor`) and submit to microsoft/winget-pkgs — why: no Wallpaper Engine extractor is on winget; Windows is the main audience
3. AUR: `wallpaper-engine-extractor` PKGBUILD built with python-build/python-installer from the release tarball — why: empty niche, low effort
4. Batch extraction in the GUI: multi-select, type filter (`scene`/`video`), skip already extracted, duplicate-title collision handling — why: `Find in Steam` already has search, and every competitor GUI with over 2k downloads has batch mode
5. Demo GIF in the README (Find in Steam → Extract → Open folder) — why: search visitors decide on the first screen
6. AlternativeTo listing as a RePKG alternative — why: discovery outside GitHub search

## Debt
<!-- Known problems we are living with. Never deleted silently: fixed, or moved to Done. -->
| ID | Problem | Risk if ignored | Fix idea |
|----|---------|-----------------|----------|
| D1 | The exe is built windowed (`console=False`, `sys.stdout` is `None`), so CLI flags passed to it print nothing (`--version`, `--list-wallpapers`). A single file opened with the exe now opens the window (2026-11-20, #12) | Users of the winget command alias think the CLI is broken | Keep docs saying the CLI is from source/pipx; or `AttachConsole` + reopen `CONOUT$` / ship a separate console shim |
| D2 | Main image is picked heuristically (first full-screen layer in scene.json, else largest texture) | Scenes built from partial layers, puppets or video backgrounds get the wrong or no main image | Compose image layers from scene.json (position, scale, alpha), roughly 12–20h |
| D3 | Unsigned PyInstaller onefile exe | Defender/SmartScreen false positives, manual review on winget | See O1 |
| D4 | `WallpaperBrowserDialog` decodes all preview thumbnails before showing the list, and only the main window has Tk smoke tests (`tests/test_gui.py`, skipped without a display) | Slow startup on Workshop libraries with 500+ items; browser regressions rely on manual checks | Lazy/incremental thumbnail decoding in batches; a smoke test for `WallpaperBrowserDialog` |

## Decisions pending
<!-- Questions only a human can settle. Each states the options and a recommendation. -->
- O1 — Code signing — options: apply to SignPath Foundation (free for OSS built in public CI) / stay unsigned with published checksums — recommend: apply after v1.2.0 ships, because winget and AV friction grow with reach

## Ideas
- Check #14 on a real Windows machine at 100% and 150% scaling, light and dark — value: DPI awareness and the DWM title bar were only exercised by CI, never looked at
<!-- Suggestions not yet committed to. Cheap to add, cheap to drop. -->
- Skip already-extracted wallpapers unless `--overwrite` (RePKG `--overwrite`) — value: re-running on a library doesn't redo everything
- `--only` / `--ignore` extension filters (RePKG `-e`/`-i`) — value: modders who want shaders or models only
- Export as an editable project (project.json, preview, `.tex-json`) — value: creators and modders, RePKG `-c` parity
- Output folders by author/title plus `metadata.json` — value: people backing up their library
- `.mpkg` (mobile) packages — value: low; their ETC textures aren't decoded by any tool yet
- GitHub Pages landing page answering "extract / get mp4 / use on Linux" — value: long-tail search traffic
- Short YouTube tutorial — value: existing guides are old and RePKG/.bat based
- Not doing: rendering animated scenes to video (100h+), promoting on the Wallpaper Engine Steam community hub (the main extraction guide there was removed for breaking its guidelines)

## Done (recent)
<!-- Last ~10 items, newest first, each with its PR/commit. Older ones: delete; git has them. -->
- 2026-11-20 — New look: neutral zinc palette (follows the Windows light/dark setting), dashed drop zone, file card with preview and status, footer actions, log behind "Show log"; crisp on scaled Windows displays (DPI aware) with a dark title bar; first Tk smoke tests (#14)
- 2026-11-20 — Path/GIF hardening, Steam scan survives unreadable drives, a file opened with the exe opens the window (#12)
- 2026-11-20 — Never open a path from a wallpaper that leaves its folder (Windows UNC/NTLM leak), skip tiny stretched textures as the main image (#13)
- 2026-10-31 — Save a copy of the scene's main image at the top of the output folder (#11)
- 2026-10-31 — Fix Linux Steam paths (Snap, `XDG_DATA_HOME`, symlink dedup), report skipped web/application wallpapers, convert loose `.tex` folders, and add `--version` (#10)
- 2026-10-30 — Installable from PyPI as `wallpaper-engine-extractor`; package renamed from `src` (#9)
- 2026-10-30 — README rewritten for end users, format notes moved to docs/FORMAT.md (#8)
- 2026-10-29 — Repo description, topics and homepage set for search (`gh repo edit`, no PR)
