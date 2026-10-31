# Wallpaper Engine Extractor — Roadmap

## Now
<!-- In progress. At most 3. Each names its branch/PR when it has one. -->
- [ ] N1 — v1.2.0: main image copy (#11) and Linux paths / CLI messages (#10) — next step: merge #10, then #11, then bump `assets/version_info.txt` to 1.2.0 and push the `v1.2.0` tag

## Next
<!-- Ordered; the top item is what starts when Now frees up. At most 10. -->
1. PyPI trusted publisher: add the pending publisher on pypi.org (workflow `publish.yml`, environment `pypi`) and create the `pypi` environment in repo settings — why: without it the tag's publish job fails (the exe release is unaffected)
2. winget: write portable manifests for 1.2.0 (`uKeps.WallpaperEngineExtractor`) and submit to microsoft/winget-pkgs — why: no Wallpaper Engine extractor is on winget; Windows is the main audience
3. AUR: `wallpaper-engine-extractor` PKGBUILD built with python-build/python-installer from the release tarball — why: empty niche, low effort
4. Batch extraction in the GUI: multi-select, search, type filter, skip already extracted — why: every competitor GUI with over 2k downloads has it
5. Demo GIF in the README (Find in Steam → Extract → Open folder) — why: search visitors decide on the first screen
6. AlternativeTo listing as a RePKG alternative — why: discovery outside GitHub search

## Debt
<!-- Known problems we are living with. Never deleted silently: fixed, or moved to Done. -->
| ID | Problem | Risk if ignored | Fix idea |
|----|---------|-----------------|----------|
| D1 | The exe is built windowed, so CLI arguments passed to it print nothing (`--version`, `--list-wallpapers`) | Users of the winget command alias think the CLI is broken | Keep docs saying the CLI is from source/pipx; or `AttachConsole` on Windows when args are given |
| D2 | Main image is picked heuristically (first full-screen layer in scene.json, else largest texture) | Scenes built from partial layers, puppets or video backgrounds get the wrong or no main image | Compose image layers from scene.json (position, scale, alpha), roughly 12–20h |
| D3 | Unsigned PyInstaller onefile exe | Defender/SmartScreen false positives, manual review on winget | See O1 |

## Decisions pending
<!-- Questions only a human can settle. Each states the options and a recommendation. -->
- O1 — Code signing — options: apply to SignPath Foundation (free for OSS built in public CI) / stay unsigned with published checksums — recommend: apply after v1.2.0 ships, because winget and AV friction grow with reach

## Ideas
<!-- Suggestions not yet committed to. Cheap to add, cheap to drop. -->
- Layer composition for the main image — value: fixes D2 for most scenes
- Export as an editable project (project.json, preview, `.tex-json`) — value: creators and modders, RePKG `-c` parity
- Output folders by author/title plus `metadata.json` — value: people backing up their library
- `.mpkg` (mobile) packages — value: low; their ETC textures aren't decoded by any tool yet
- GitHub Pages landing page answering "extract / get mp4 / use on Linux" — value: long-tail search traffic
- Short YouTube tutorial — value: existing guides are old and RePKG/.bat based
- Not doing: rendering animated scenes to video (100h+), promoting on the Wallpaper Engine Steam community hub (the main extraction guide there was removed for breaking its guidelines)

## Done (recent)
<!-- Last ~10 items, newest first, each with its PR/commit. Older ones: delete; git has them. -->
- 2026-10-30 — Installable from PyPI as `wallpaper-engine-extractor`; package renamed from `src` (#9)
- 2026-10-30 — README rewritten for end users, format notes moved to docs/FORMAT.md (#8)
- 2026-10-29 — Repo description, topics and homepage set for search (`gh repo edit`, no PR)
