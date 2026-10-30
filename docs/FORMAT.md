# How Wallpaper Engine stores wallpapers

Technical notes behind the extractor. You don't need any of this to use the app.

## Where the files live

Each Steam Workshop wallpaper gets its own folder, named after its Workshop ID:

```
<Steam library>\steamapps\workshop\content\431960\<workshop_id>\
```

`431960` is Wallpaper Engine's Steam app ID. The default Steam library on Windows is `C:\Program Files (x86)\Steam`. The extractor finds Steam through the Windows registry and the standard install paths on Windows, Linux (including Flatpak) and macOS, and reads `steamapps/libraryfolders.vdf` to check every Steam library.

| File | What it is |
|---|---|
| `project.json` | Metadata: title, type (`scene`, `video`, `web`, `application`), main file, preview |
| `scene.pkg` | Scene wallpapers: package holding the textures, shaders, scripts and scene description |
| `*.mp4` / `*.webm` | Video wallpapers: the video itself, not packed |
| `preview.jpg` (or `.png`/`.gif`) | Thumbnail shown in Wallpaper Engine and in **Find in Steam** |

## `.pkg`

A plain binary archive:

1. A length-prefixed version string (`PKGV0024`-style)
2. A uint32 file count
3. One entry per file: length-prefixed name, uint32 offset, uint32 size
4. All file data, concatenated. Offsets count from the end of the entry table.

All integers are little-endian.

## `.tex`

1. A `TEXV` version tag.
2. `TEXI`: pixel format, flags, padded texture size and real image size.
3. A `TEXB` container (`TEXB0001` to `TEXB0004`) with one or more images. Each image is a list of mipmaps.
4. Animated textures only: a `TEXS` section listing the frames on a sprite sheet.

Each mipmap is one of:

- **Raw pixels** in the `TEXI` format: DXT1, DXT3, DXT5, RGBA8888, RG88 or R8. They're often LZ4-compressed.
- **A complete embedded file**: PNG, JPG, MP4 and so on, written out as it is.

Raw pixels are decoded and cropped from the padded size to the real image size, then saved as PNG with Pillow or as a hand-built BMP without it. Animated textures are saved as the sprite sheet, plus a `.gif` built from the `TEXS` frames when Pillow is installed.

The layout follows [RePKG](https://github.com/notscuffed/repkg), which is the reference implementation. The decoder here is a standalone Python reimplementation of it, including a pure-Python LZ4 block decoder, so it doesn't need RePKG or .NET. Pillow is optional: without it, DXT decoding falls back to pure Python too.

## Video wallpapers

No `.pkg` is involved, because the `.mp4`/`.webm` already sits loose in the Workshop folder. "Extracting" a video wallpaper just copies that file.

## Web and application wallpapers

A web wallpaper is an HTML page and an application wallpaper is a program. Neither has a single image or video to extract, so the app lists them but doesn't extract them.
