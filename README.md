<img src="assets/icon.png" width="50" align="right" alt="">

# Wallpaper Engine PKG Extractor

Extracts the image (or video) from wallpapers downloaded by Wallpaper Engine, no extra software needed.

When you subscribe to a wallpaper on the Steam Workshop, the downloaded files come in a proprietary format (`scene.pkg`, containing `.tex` textures inside) or, for video wallpapers, as a plain `.mp4`/`.webm` file. This script reads the `scene.pkg`, decodes the `.tex` textures, and saves everything as regular PNG/JPG/BMP. Videos are just copied out as-is.

## Download

Grab **`WallpaperExtractor.exe`** from the [Releases page](https://github.com/uKeps/wallpaper-pkg-extractor/releases/latest). It's a single self-contained file — no Python, no install, just double-click it.

The `.exe` ships the GUI only. For the command line, use the source version.

### Windows will complain, and that's expected

The executable is **not code-signed**. A code signing certificate is a paid, yearly subscription, which is hard to justify for a free tool — so Windows treats the file as coming from an unknown publisher. Two different things can happen:

**SmartScreen warning** — a blue "Windows protected your PC" box. This is just a warning: click **More info → Run anyway** and it runs. Most people will only ever see this one.

**Smart App Control block** — "An Application Control policy has blocked this file". This one is a hard block, with no "run anyway" button. Smart App Control is enabled by default on clean installs of Windows 11 22H2 and newer, and for unsigned files its verdict comes from Microsoft's cloud reputation service, so it can block one build and allow the next.

If you hit the hard block, **use the source version instead** — every release has a `Source code (zip)` asset attached, and the [Installation](#installation) section below takes two minutes. Please **don't turn Smart App Control off** to work around this: it can only be re-enabled by reinstalling Windows, which is a terrible trade for one small utility.

Each release also ships a `checksums.txt` with the SHA256 of the `.exe`, so you can confirm the file you downloaded is byte-for-byte the one built by GitHub Actions:

```powershell
Get-FileHash WallpaperExtractor.exe -Algorithm SHA256
```

## Features

- No dependencies needed for most cases (PNG/JPG textures work out of the box)
- GUI (run `main.py` with no arguments) and also works from the command line
- Auto-detects installed wallpapers via Steam, with preview thumbnails, no manual folder hunting
- Drag and drop files onto the GUI window
- Extracts videos (`.mp4`/`.webm`) by copying them out
- Works with any version of the `.tex` format — no hardcoded offsets, layout is detected dynamically
- "Images only" mode: deletes shaders, scripts and JSON, keeping just the wallpaper
- Pillow (optional) to convert RAW/RLE textures to PNG and generate preview thumbnails
- tkinterdnd2 (optional) to enable drag & drop in the GUI

## Installation

Only needed if you want the CLI or prefer running from source — otherwise just [download the .exe](#download).

Requires [Python 3.10+](https://www.python.org/downloads/) (check "Add Python to PATH" during install).

```bash
git clone https://github.com/uKeps/wallpaper-pkg-extractor.git
cd wallpaper-pkg-extractor
pip install -r requirements.txt
```

The `pip install` step is optional — without it, PNG and JPG still extract fine, only the rarer RAW/RLE textures come out as BMP instead of PNG, and drag & drop is disabled.

## Where the files live

Steam stores downloaded wallpapers here:

```
C:\Program Files (x86)\Steam\steamapps\workshop\content\431960\<wallpaper_ID>\
```

Inside each folder:

| File | What it is |
|---|---|
| `scene.pkg` | The package with the wallpaper's assets |
| `preview.jpg` | Preview thumbnail |
| `project.json` | Wallpaper metadata |

In practice you don't need to hunt for this manually — the GUI's auto-detect button (or `--list-wallpapers` in the CLI) already lists everything for you.

## Usage

### GUI

```bash
python main.py
```

1. Click **Browse** and pick the `scene.pkg`, `.tex`, or video file — or drag the file onto the window, or click **Detect Installed Wallpapers (Steam)** to pick one from a list with previews
2. Check the output folder (already filled in next to the input file)
3. Leave **"Keep ONLY wallpaper images"** checked if you just want the image, without the extra files (only affects scene-type wallpapers)
4. Click **Extract & Convert Assets**

Web-type wallpapers show up in the detection list but can't be extracted — they don't have a fixed asset to pull out.

### CLI

```bash
# basic extraction — outputs to scene_extracted/ next to the .pkg
python main.py "path/to/scene.pkg"

# custom output folder
python main.py "path/to/scene.pkg" -o "C:/Users/YourName/Desktop/output"

# extract a standalone .tex file
python main.py "path/to/texture.tex" -o "C:/Users/YourName/Desktop/output"

# keep all files (don't delete shaders, JSON, etc.)
python main.py "path/to/scene.pkg" --no-cleanup

# also extract smaller mipmap sizes, not just the max resolution
python main.py "path/to/scene.pkg" --all-mipmaps

# copy out a video wallpaper
python main.py "path/to/video.mp4" -o "C:/Users/YourName/Desktop/output"

# force open the GUI even when passing arguments
python main.py --gui

# list installed wallpapers (title, ID, type, asset path)
python main.py --list-wallpapers
```

Full reference:

```
positional arguments:
  input                 Path to scene.pkg, a standalone .tex file, or a video wallpaper (.mp4/.webm)

options:
  -h, --help            Show this help message and exit
  -o, --output PATH     Output directory (default: <name>_extracted next to input)
  --no-tex-convert      Skip converting extracted .tex files to PNG/JPG
  --all-mipmaps         Extract all mipmap levels, not just the highest resolution
  --no-cleanup          Keep all extracted files (shaders, JSON, scripts, etc.)
  --gui                 Force launch the GUI even when arguments are provided
  --list-wallpapers     List installed Wallpaper Engine Steam Workshop wallpapers and exit
```

## Building the executable

```powershell
.\build.ps1
```

Installs PyInstaller if needed and writes `dist\WallpaperExtractor.exe` (~17 MB, single file, no console window). Everything is bundled — Python, Tk, Pillow and the `tkdnd` Tcl package that drag & drop depends on.

Pushing a `v*` tag builds it on GitHub Actions and attaches the `.exe` plus a `checksums.txt` to the release automatically (`.github/workflows/build.yml`); the same workflow can be run manually from the Actions tab.

Builds are unsigned — see [the warning above](#windows-will-complain-and-thats-expected) for what that means for users. If signing ever becomes worth the trouble, [SignPath Foundation](https://signpath.org/) grants free code signing certificates to open source projects that build in public CI, which is the only route that actually clears SmartScreen and Smart App Control without a yearly bill.

## Project structure

```
wallpaper-pkg-extractor/
├── main.py                    # entry point — dispatches to GUI or CLI
├── requirements.txt           # optional dependencies (Pillow, tkinterdnd2)
├── build.ps1                  # builds the .exe
├── WallpaperExtractor.spec    # PyInstaller config
├── assets/                    # app icon and Windows version resource
├── LICENSE
├── README.md
└── src/
    ├── extractor.py          # .pkg parser
    ├── tex_parser.py         # .tex decoder and image conversion
    ├── steam_finder.py       # scans Steam libraries/Workshop
    ├── wallpaper_browser.py  # GUI window listing detected wallpapers
    ├── video_extractor.py    # copies out video wallpapers
    └── gui.py                # Tkinter GUI
```

## How it works under the hood

**`.pkg` format**: a simple binary archive — a string with the root path (something like `PKGV0024`, identifies the Wallpaper Engine version), a uint32 with the file count, then the entries (name, offset, size), and finally all file data concatenated together.

**`.tex` format**: a texture container with three sections — `TEXV` (version), `TEXI` (width/height), and `TEXB` (mipmap binary data). Each mipmap stores width, height, size, and the image bytes, which can be raw PNG, raw JPG, or RLE-compressed BGRA. Instead of using hardcoded offsets (which break between versions), the script scans for the `(width, height)` byte pattern right after the `TEXB` marker to find the first mipmap — that's why it works across any version of the format.

**Videos**: don't use a `.pkg` at all, the `.mp4`/`.webm` file already sits loose in the Workshop folder. "Extracting" here is just copying it to the chosen destination.

## Disclaimer

This is for personal use — like recovering the image of a wallpaper you already own. Respect the creators' copyright and don't redistribute extracted assets without permission.

## License

[MIT](LICENSE) © uKeps
