<img src="https://raw.githubusercontent.com/uKeps/wallpaper-engine-extractor/master/assets/icon.png" width="64" align="right" alt="">

# Wallpaper Engine Extractor

Get the original image or video out of a Wallpaper Engine wallpaper. It unpacks `scene.pkg` and converts `.tex` textures to normal images, so you can use the picture as a regular desktop or phone background.

[![Latest release](https://img.shields.io/github/v/release/uKeps/wallpaper-engine-extractor?label=version)](https://github.com/uKeps/wallpaper-engine-extractor/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/uKeps/wallpaper-engine-extractor/total)](https://github.com/uKeps/wallpaper-engine-extractor/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/uKeps/wallpaper-engine-extractor/blob/master/LICENSE)

<p align="center">
  <a href="https://github.com/uKeps/wallpaper-engine-extractor/releases/latest/download/WallpaperExtractor.exe">
    <img src="https://img.shields.io/badge/Download_for_Windows-WallpaperExtractor.exe-2563eb?style=for-the-badge&logo=windows" alt="Download WallpaperExtractor.exe for Windows">
  </a>
  <br>
  <sub>Windows 10 and 11 · one file, no install · no Python, .NET or RePKG needed · <a href="#is-it-safe-windows-says-it-protected-my-pc">is it safe?</a></sub>
</p>

<p align="center"><img src="https://raw.githubusercontent.com/uKeps/wallpaper-engine-extractor/master/assets/screenshot.png" width="460" alt="Wallpaper Engine Extractor after extracting a wallpaper"></p>

## How to use

1. Open `WallpaperExtractor.exe`.
2. Click **Find in Steam** and pick a wallpaper from the list (it finds every wallpaper you've downloaded, with thumbnails). Or drag its Workshop folder onto the window.
3. Click **Extract**, then **Open folder**.

Your files land in **`Desktop\Wallpaper Extracted\<wallpaper title>`**. Click **Change** to save somewhere else.

## What you get

- **Scene wallpapers:** every image inside, as PNG (or JPG, when that's how it was packed). Animated textures also come out as a `.gif`.
- **Video wallpapers:** the original `.mp4` or `.webm`, copied out.
- **Just the pictures:** "Only keep images and videos" (on by default) throws away shaders, scripts and settings files.

Compressed, LZ4-packed and animated textures are all handled. Details are in [docs/FORMAT.md](https://github.com/uKeps/wallpaper-engine-extractor/blob/master/docs/FORMAT.md).

## FAQ

#### Where are my files?

In `Wallpaper Extracted` on your Desktop, one folder per wallpaper, named after its title. Click **Open folder** after extracting to jump straight there.

#### Why do I get several images instead of one?

A scene wallpaper is built from layers: a background, plus things like rain, particles or a character drawn on top. Wallpaper Engine combines and animates them live. The extractor gives you each layer as its own image. The background is usually the largest file. The live effects can't be saved as a picture, so record your screen if you want the animated version.

#### Does it work on web or application wallpapers?

No. They show up in the list but can't be extracted. A web wallpaper is a web page and an application wallpaper is a program, so neither has an image or video file to pull out. Scene and video wallpapers both work.

#### Do I need to own Wallpaper Engine?

Yes. The extractor reads wallpapers that Wallpaper Engine has already downloaded through the Steam Workshop. Subscribe to a wallpaper first, then it shows up under **Find in Steam**.

#### Is it safe? Windows says it "protected my PC"

The exe isn't code signed. Signing costs money every year, which is hard to justify for a free tool. Because of that, Windows shows a warning for any new download from an unknown publisher.

- **"Windows protected your PC" (blue screen):** click **More info**, then **Run anyway**.
- **Blocked by Smart App Control with no "Run anyway" button** (some Windows 11 PCs): [run it from source](#run-from-source-linux-macos-command-line) instead. Don't turn Smart App Control off for this: on many PCs it can't be turned back on without reinstalling Windows.

The exe is built from this repository's source by GitHub Actions. Each release includes a `checksums.txt` so you can check that your download matches: run `Get-FileHash WallpaperExtractor.exe` in PowerShell and compare the hash.

#### Does it work on Linux or macOS?

There's no Linux or macOS download, but the app runs from source on both ([see below](#run-from-source-linux-macos-command-line)). **Find in Steam** checks the usual Steam folders on Linux, including Flatpak Steam, and on macOS.

#### How is this different from RePKG?

[RePKG](https://github.com/notscuffed/repkg) is the command-line tool this project's texture decoding is modeled on. This app is a standalone reimplementation with a window, Steam auto-detection and a one-click extract, so you don't need to download RePKG or use a terminal.

## Run from source (Linux, macOS, command line)

You need [Python 3.10+](https://www.python.org/downloads/). On Windows, check "Add Python to PATH" during install. On Linux, the window also needs your distro's Tk package (`python3-tk` on Debian/Ubuntu); the command line works without it.

```bash
git clone https://github.com/uKeps/wallpaper-engine-extractor.git
cd wallpaper-engine-extractor
pip install -r requirements.txt   # optional
python main.py                    # opens the app
```

`pip install` is optional. Without it, extraction still works, but decoded textures are saved as BMP instead of PNG, there's no `.gif` for animated textures, no thumbnails in the Steam list, and no drag and drop.

<details>
<summary><b>Command line</b></summary>

```bash
python main.py --list-wallpapers                    # installed wallpapers: title, ID, type, file
python main.py "path/to/scene.pkg"                  # output goes to scene_extracted/ next to the .pkg
python main.py "path/to/scene.pkg" -o out           # choose the output folder
python main.py "path/to/texture.tex" -o out         # a single .tex, or an .mp4/.webm, works the same way
python main.py ".../workshop/content/431960" -o out # a whole folder: one subfolder per wallpaper
```

| Option | What it does |
|---|---|
| `-o, --output PATH` | Output folder. Default: `<name>_extracted` next to a `.pkg` or folder, and the input's own folder for a `.tex` or video |
| `--no-tex-convert` | Keep `.tex` files as they are |
| `--all-mipmaps` | Save every mipmap size, not just the largest |
| `--no-cleanup` | Keep shaders, JSON, scripts and other non-image files |
| `--gui` | Open the app even when arguments are given |
| `--list-wallpapers` | List installed Wallpaper Engine wallpapers and exit |

</details>

To contribute or build the exe, see [CONTRIBUTING.md](https://github.com/uKeps/wallpaper-engine-extractor/blob/master/CONTRIBUTING.md).

## Disclaimer

For personal use, like saving the picture of a wallpaper you're subscribed to. Wallpapers belong to their creators. Don't redistribute extracted files without the creator's permission.

## License

[MIT](https://github.com/uKeps/wallpaper-engine-extractor/blob/master/LICENSE) © uKeps
