<img src="assets/icon.png" width="50" align="right" alt="">

# Wallpaper Engine PKG Extractor

Extracts the image (or video) from wallpapers downloaded by Wallpaper Engine.

Downloaded workshop wallpapers use a proprietary format: `scene.pkg` with `.tex` textures inside, or a plain `.mp4`/`.webm` for video wallpapers. This tool reads the `.pkg`, decodes the `.tex` textures, and saves everything as PNG/JPG/BMP. Videos are just copied out as-is.

## Download

Grab `WallpaperExtractor.exe` from the [Releases page](https://github.com/uKeps/wallpaper-pkg-extractor/releases/latest). Single file, no install, no Python needed.

The `.exe` only has the GUI. For the CLI, run from source.

### About the Windows warnings

The exe isn't code signed (a signing certificate costs money every year, hard to justify for a free tool), so Windows treats it as coming from an unknown publisher.

Usually you'll just see a blue "Windows protected your PC" SmartScreen warning. Click **More info → Run anyway** and it works.

On some Windows 11 22H2+ installs, Smart App Control is on by default and can hard block the exe with no "run anyway" option, based on Microsoft's cloud reputation for that specific file. If that happens, use the source version instead (see [Installation](#installation), it's quick). Don't disable Smart App Control just for this, since turning it back on means reinstalling Windows.

Each release ships a `checksums.txt` so you can verify the exe:

```powershell
Get-FileHash WallpaperExtractor.exe -Algorithm SHA256
```

## Features

- Works out of the box for PNG/JPG textures, no dependencies
- GUI (`main.py` with no args) or CLI
- Auto-detects installed wallpapers via Steam, with thumbnails
- Drag and drop onto the GUI window
- Extracts video wallpapers (`.mp4`/`.webm`)
- Handles any `.tex` format version, no hardcoded offsets
- "Images only" mode strips shaders/scripts/JSON, keeps just the wallpaper
- Optional: Pillow for RAW/RLE → PNG conversion and thumbnails, tkinterdnd2 for drag & drop

## Installation

Only needed for the CLI or to run from source, otherwise just [download the exe](#download).

Requires [Python 3.10+](https://www.python.org/downloads/) (check "Add Python to PATH" during install).

```bash
git clone https://github.com/uKeps/wallpaper-pkg-extractor.git
cd wallpaper-pkg-extractor
pip install -r requirements.txt
```

`pip install` is optional. Without it, PNG/JPG still extract fine, RAW/RLE textures fall back to BMP, and drag & drop is disabled.

## Where the files live

```
C:\Program Files (x86)\Steam\steamapps\workshop\content\431960\<wallpaper_ID>\
```

| File | What it is |
|---|---|
| `scene.pkg` | Package with the wallpaper's assets |
| `preview.jpg` | Preview thumbnail |
| `project.json` | Wallpaper metadata |

The GUI's auto-detect button (or `--list-wallpapers` in the CLI) lists all of this for you, no need to dig through folders manually.

## Usage

### GUI

```bash
python main.py
```

1. Browse or drag in a `scene.pkg`, `.tex`, or video file, or click **Detect Installed Wallpapers (Steam)**
2. Check the output folder (auto-filled next to the input)
3. Leave "Keep ONLY wallpaper images" checked if you just want the image (scene-type wallpapers only)
4. Click **Extract & Convert Assets**

Web-type wallpapers show up in the detection list but can't be extracted, they don't have a fixed asset to pull.

### CLI

```bash
# basic extraction, outputs to scene_extracted/ next to the .pkg
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

Installs PyInstaller if needed, writes `dist\WallpaperExtractor.exe` (~17 MB, single file, no console). Python, Tk, Pillow and the `tkdnd` Tcl package all get bundled in.

Pushing a `v*` tag builds it on GitHub Actions and attaches the exe plus `checksums.txt` to the release (`.github/workflows/build.yml`). Can also be run manually from the Actions tab.

Builds are unsigned, see the warning section above. [SignPath Foundation](https://signpath.org/) gives free signing certs to open source projects that build in public CI, that's the only route that actually clears SmartScreen and Smart App Control without paying yearly.

## Project structure

```
wallpaper-pkg-extractor/
├── main.py                    # entry point, dispatches to GUI or CLI
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

## How it works

**`.pkg`**: binary archive. Root path string (`PKGV0024`-style, identifies the WE version), a uint32 file count, then entries (name, offset, size), then all file data concatenated.

**`.tex`**: three sections, `TEXV` (version), `TEXI` (width/height), `TEXB` (mipmap data). Each mipmap has width, height, size and image bytes, either raw PNG, raw JPG, or RLE-compressed BGRA. Instead of hardcoded offsets, which break between format versions, the script scans for the `(width, height)` byte pattern right after `TEXB` to find the first mipmap. That's what makes it version-agnostic.

**Video**: no `.pkg` involved, the `.mp4`/`.webm` already sits loose in the Workshop folder. "Extracting" is just a copy.

## Disclaimer

For personal use, like recovering the image of a wallpaper you already own. Respect creators' copyright, don't redistribute extracted assets without permission.

## License

[MIT](LICENSE) © uKeps
