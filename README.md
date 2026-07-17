# 🖼️ Wallpaper Engine PKG Extractor

> Extract the wallpaper image from Wallpaper Engine's `scene.pkg` archives — no extra software needed.

[![Python](https://img.shields.io/badge/Python-3.6%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()

---

When you subscribe to a wallpaper on the Wallpaper Engine Steam Workshop, the files are downloaded as a proprietary `scene.pkg` archive (or, for video wallpapers, a plain `.mp4`/`.webm` file). This tool unpacks `scene.pkg` archives and converts the internal `.tex` texture files into standard image formats (PNG / JPG / BMP), and copies out video wallpapers as-is — all without extra software.

## ✨ Features

- **Zero dependencies** for most wallpapers (PNG/JPG textures work out of the box)
- **GUI included** — just double-click `main.py` to open the visual interface
- **Auto-detect installed Steam wallpapers** — scans every Steam library for Wallpaper Engine Workshop items and lists them with preview thumbnails, no manual folder hunting required
- **Video wallpaper support** — copies out `.mp4`/`.webm` video wallpapers alongside scene/`.pkg` extraction
- **CLI support** — great for scripting and batch processing
- **Compatible with all TEX versions** — dynamically detects mipmap layouts instead of using hardcoded offsets
- **Image-only mode** — automatically deletes shaders, scripts and JSON files, keeping only the wallpaper images
- **Optional Pillow support** — install `pillow` to convert RAW/RLE textures to PNG and to render preview thumbnails

---

## 🚀 Quick Start

### 1. Requirements

- [Python 3.6+](https://www.python.org/downloads/) — make sure to check **"Add Python to PATH"** during installation

### 2. Clone the repository

```bash
git clone https://github.com/uKeps/wallpaper-pkg-extractor.git
cd wallpaper-pkg-extractor
```

### 3. (Optional) Install Pillow for full RAW texture support

```bash
pip install -r requirements.txt
```

> Without Pillow, PNG and JPG wallpapers extract perfectly. Only uncommon RAW/RLE textures will be saved as BMP instead of PNG.

---

## 🗂️ Finding Your Wallpaper Files

Steam stores Wallpaper Engine workshop downloads here:

```
C:\Program Files (x86)\Steam\steamapps\workshop\content\431960\<Wallpaper_ID>\
```

Inside each wallpaper folder you'll find:
| File | Description |
|------|-------------|
| `scene.pkg` | The archive containing all wallpaper assets |
| `preview.jpg` | Small preview thumbnail |
| `project.json` | Wallpaper metadata |

---

## 🖥️ Usage

### Graphical Interface (GUI)

Run without arguments to open the visual interface:

```bash
python main.py
```

1. Click **Browse** next to *Input File* and select your `scene.pkg`, `.tex`, or video wallpaper file — or click **Detect Installed Wallpapers (Steam)** to pick one from a list of your subscribed Workshop items with preview thumbnails
2. Set the *Output Folder* (default is auto-filled next to the input file)
3. Keep **"Keep ONLY wallpaper images"** checked to skip shaders/scripts (scene wallpapers only)
4. Click **Extract & Convert Assets**

#### Auto-detecting installed wallpapers

The **Detect Installed Wallpapers (Steam)** button scans every Steam library (read from the registry and `libraryfolders.vdf`) for `steamapps/workshop/content/431960`, the Wallpaper Engine Workshop app ID. Each entry shows its preview thumbnail (requires Pillow), title, Workshop ID and type; clicking **Select** fills in the input/output fields automatically for both `scene` wallpapers (`scene.pkg`) and `video` wallpapers (`.mp4`/`.webm`). Web wallpapers are listed too but can't be selected since they have no extractable asset.

### Command Line (CLI)

```bash
# Basic extraction — outputs to scene_extracted/ next to the .pkg
python main.py "path/to/scene.pkg"

# Custom output folder
python main.py "path/to/scene.pkg" -o "C:/Users/YourName/Desktop/output"

# Extract a standalone .tex texture file
python main.py "path/to/texture.tex" -o "C:/Users/YourName/Desktop/output"

# Keep ALL files (don't delete shaders, JSON, etc.)
python main.py "path/to/scene.pkg" --no-cleanup

# Also extract smaller mipmap sizes (not just full resolution)
python main.py "path/to/scene.pkg" --all-mipmaps

# Copy out a video wallpaper (.mp4/.webm)
python main.py "path/to/video_wallpaper.mp4" -o "C:/Users/YourName/Desktop/output"

# Force open the GUI
python main.py --gui

# List installed Steam Workshop wallpapers (title, ID, type, extractable asset path)
python main.py --list-wallpapers
```

### Full CLI Reference

```
positional arguments:
  input                 Path to scene.pkg, a standalone .tex file, or a video wallpaper (.mp4/.webm)

options:
  -h, --help            Show this help message and exit
  -o, --output PATH     Output directory (default: <name>_extracted next to input)
  --no-tex-convert      Skip converting .tex files to PNG/JPG
  --all-mipmaps         Extract all mipmap levels, not just the highest resolution
  --no-cleanup          Keep all extracted files (shaders, JSON, scripts, etc.)
  --gui                 Force launch the GUI even when arguments are provided
  --list-wallpapers     List installed Wallpaper Engine Steam Workshop wallpapers and exit
```

---

## 📁 Project Structure

```
wallpaper-pkg-extractor/
├── main.py               # Entry point — dispatches to GUI or CLI
├── requirements.txt      # Optional dependency (Pillow)
├── LICENSE
├── README.md
└── src/
    ├── __init__.py
    ├── extractor.py          # .pkg archive parser and file extractor
    ├── tex_parser.py         # .tex container decoder and image converter
    ├── steam_finder.py       # Steam library/Workshop scanner for installed wallpapers
    ├── wallpaper_browser.py  # GUI dialog listing detected wallpapers with thumbnails
    ├── video_extractor.py    # Copies out .mp4/.webm video wallpapers
    └── gui.py                # Tkinter dark-themed GUI
```

---

## 🔧 How It Works

### `.pkg` Format

Wallpaper Engine `.pkg` files are simple binary archives:
1. **Root path** — length-prefixed UTF-8 string (identifies the WE version, e.g. `PKGV0024`)
2. **File count** — 4-byte little-endian uint32
3. **File entries** — each has a length-prefixed name, a 4-byte offset, and a 4-byte size
4. **Raw data** — all file contents concatenated sequentially

### `.tex` Format

`.tex` files are texture containers with three sections:
- `TEXV` — version header
- `TEXI` — metadata (base width and height)
- `TEXB` — binary texture data (mipmaps)

Each mipmap stores width, height, data size, then the actual image bytes. The image can be a raw PNG, raw JPG, or RLE-compressed BGRA data.

This tool uses a **dynamic scanning strategy** — it locates the first mipmap by searching for the `(width, height)` byte pattern after the `TEXB` marker, making it work across all known Wallpaper Engine versions.

### Video Wallpapers

Video wallpapers don't use a `.pkg` container at all — the Workshop folder holds the finished `.mp4`/`.webm` file directly. There's nothing to parse, so "extracting" one just copies it into the chosen output folder unchanged.

---

## ⚠️ Disclaimer

This tool is intended for **personal use only** — for example, recovering a wallpaper image you already own. Please respect the copyright and creative work of wallpaper creators. Do not redistribute extracted assets without permission.

---

## 📄 License

[MIT](LICENSE) © uKeps
